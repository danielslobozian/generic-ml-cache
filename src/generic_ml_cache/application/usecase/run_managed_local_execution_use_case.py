# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunManagedLocalExecutionUseCase."""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional, Tuple

from generic_ml_cache.application.domain.model.artifact import Artifact, ArtifactType
from generic_ml_cache.application.domain.model.cache_mode import CacheMode
from generic_ml_cache.application.domain.model.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.client_run_request import ClientRunRequest
from generic_ml_cache.application.domain.model.client_run_result import ClientRunResult
from generic_ml_cache.application.domain.model.execution_failure import (
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache.application.domain.model.execution_kind import ExecutionKind
from generic_ml_cache.application.domain.model.execution_state import ExecutionState
from generic_ml_cache.application.domain.model.ml_execution import MlExecution
from generic_ml_cache.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache.application.port.out.client_runner_port import ClientRunnerPort
from generic_ml_cache.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache.application.port.out.metrics_port import MetricsPort
from generic_ml_cache.application.usecase import journal_events
from generic_ml_cache.application.usecase.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)
from generic_ml_cache.common.checksum import file_content_fingerprint, text_checksum
from generic_ml_cache.common.errors import ArtifactBlobMissing, CacheMiss

_CLIENT_ARGS_SEPARATOR = "\x00"


class RunManagedLocalExecutionUseCase:
    """Record-or-replay a fully managed local ML client call.

    Orchestrates five outbound ports — it fingerprints inputs, builds the
    CallIdentity, resolves the cache under the requested mode, runs the client
    on a miss, stores the output as content-addressed artifacts, journals one
    event, and returns the hydrated MlExecution. The rules live on the domain
    objects; the I/O lives behind the ports; this use case only decides what
    happens in what order.
    """

    def __init__(
        self,
        file_fingerprint: FileFingerprintPort,
        client_runner: ClientRunnerPort,
        blob_store: BlobStorePort,
        repository: ExecutionRepositoryPort,
        metrics: MetricsPort,
    ) -> None:
        self._file_fingerprint = file_fingerprint
        self._client_runner = client_runner
        self._blob_store = blob_store
        self._repository = repository
        self._metrics = metrics

    def execute(self, command: RunManagedLocalExecutionCommand) -> MlExecution:
        call_identity = self._build_call_identity(command)
        execution_key = call_identity.generate_key()

        if self._is_uncacheable(command):
            return self._run_uncacheable(command, call_identity, execution_key)

        if command.cache_mode is CacheMode.OFFLINE:
            return self._serve_offline(command, call_identity, execution_key)

        if command.cache_mode is CacheMode.CACHE:
            current = self._repository.find_current(execution_key)
            if current is not None:
                return self._serve_hit(command, execution_key, current)

        return self._run_fresh(command, call_identity, execution_key, allow_store=True)

    # -- identity ---------------------------------------------------------

    def _build_call_identity(self, command: RunManagedLocalExecutionCommand) -> CallIdentity:
        input_file_fingerprints = {
            path: self._file_fingerprint.fingerprint(path) for path in command.input_file_paths
        }
        return CallIdentity(
            client=command.client,
            model=command.model,
            effort=command.effort,
            context_fingerprint=text_checksum(command.context),
            prompt_fingerprint=text_checksum(command.prompt),
            input_file_fingerprints=input_file_fingerprints,
            client_args_fingerprint=self._fingerprint_client_args(command.client_args),
            grants=frozenset(command.grants),
        )

    @staticmethod
    def _fingerprint_client_args(client_args: List[str]) -> Optional[str]:
        if not client_args:
            return None
        return text_checksum(_CLIENT_ARGS_SEPARATOR.join(client_args))

    @staticmethod
    def _is_uncacheable(command: RunManagedLocalExecutionCommand) -> bool:
        """Declaring allow-path folders makes the call non-cacheable unless the
        caller takes responsibility with scan_trust."""
        return bool(command.allow_paths) and not command.scan_trust

    # -- resolution paths -------------------------------------------------

    def _serve_offline(
        self,
        command: RunManagedLocalExecutionCommand,
        call_identity: CallIdentity,
        execution_key: str,
    ) -> MlExecution:
        current = self._repository.find_current(execution_key)
        if current is None:
            self._record(journal_events.MISS, execution_key, command)
            raise CacheMiss(f"offline miss: no stored execution for key {execution_key}")
        return self._serve_hit(command, execution_key, current)

    def _serve_hit(
        self,
        command: RunManagedLocalExecutionCommand,
        execution_key: str,
        current: MlExecution,
    ) -> MlExecution:
        hydrated = self._hydrate(current)
        self._record(journal_events.HIT, execution_key, command)
        return hydrated

    def _run_uncacheable(
        self,
        command: RunManagedLocalExecutionCommand,
        call_identity: CallIdentity,
        execution_key: str,
    ) -> MlExecution:
        if command.cache_mode is CacheMode.OFFLINE:
            self._record(journal_events.MISS, execution_key, command)
            raise CacheMiss(
                "offline: this call declares allow-path folders the cache cannot "
                "fingerprint, so it is never cached and cannot be served offline"
            )
        return self._run_fresh(command, call_identity, execution_key, allow_store=False)

    def _run_fresh(
        self,
        command: RunManagedLocalExecutionCommand,
        call_identity: CallIdentity,
        execution_key: str,
        allow_store: bool,
    ) -> MlExecution:
        result = self._client_runner.run(self._build_client_run_request(command))
        execution_state, failure = self._interpret(result)
        should_store = self._should_store(command, execution_state, allow_store)
        artifacts = self._build_artifacts(result, store=should_store)
        execution = MlExecution(
            call_identity=call_identity,
            execution_state=execution_state,
            execution_kind=ExecutionKind.LOCAL_MANAGED,
            output_persisted=should_store,
            artifacts=artifacts,
            failure=failure,
        )
        if should_store:
            self._repository.save(execution)
            self._record(journal_events.RECORD, execution_key, command)
        else:
            self._record(journal_events.RUN, execution_key, command)
        return execution

    @staticmethod
    def _should_store(
        command: RunManagedLocalExecutionCommand,
        execution_state: ExecutionState,
        allow_store: bool,
    ) -> bool:
        if not allow_store or not command.persist_output:
            return False
        succeeded = execution_state is ExecutionState.SUCCESS
        return succeeded or command.record_on_error

    # -- client run -------------------------------------------------------

    @staticmethod
    def _build_client_run_request(command: RunManagedLocalExecutionCommand) -> ClientRunRequest:
        return ClientRunRequest(
            client=command.client,
            model=command.model,
            effort=command.effort,
            context=command.context,
            prompt=command.prompt,
            user_system_prompt=command.user_system_prompt,
            allow_paths=command.allow_paths,
            client_args=command.client_args,
            grants=frozenset(command.grants),
        )

    @staticmethod
    def _interpret(result: ClientRunResult) -> Tuple[ExecutionState, Optional[ExecutionFailure]]:
        if result.exit_code == 0:
            return ExecutionState.SUCCESS, None
        failure = ExecutionFailure(
            reason=FailureReason.NONZERO_EXIT,
            message=f"client exited with status {result.exit_code}",
            exit_code=result.exit_code,
        )
        return ExecutionState.FAILED, failure

    # -- artifacts (store) ------------------------------------------------

    def _build_artifacts(self, result: ClientRunResult, store: bool) -> List[Artifact]:
        artifacts = [
            self._make_artifact(ArtifactType.STDOUT, None, result.stdout.encode("utf-8"), store),
            self._make_artifact(ArtifactType.STDERR, None, result.stderr.encode("utf-8"), store),
        ]
        for generated_file in result.files:
            artifacts.append(
                self._make_artifact(
                    ArtifactType.OUTPUT_FILE, generated_file.name, generated_file.content, store
                )
            )
        return artifacts

    def _make_artifact(
        self, artifact_type: ArtifactType, name: Optional[str], content: bytes, store: bool
    ) -> Artifact:
        blob_key = file_content_fingerprint(content)
        if store:
            self._blob_store.put(blob_key, content)
        return Artifact(
            artifact_type=artifact_type,
            blob_key=blob_key,
            size_bytes=len(content),
            name=name,
            encoding=self._encoding_of(content),
            content=content,
        )

    @staticmethod
    def _encoding_of(content: bytes) -> str:
        try:
            content.decode("utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            return "binary"

    # -- artifacts (hydrate) ----------------------------------------------

    def _hydrate(self, execution: MlExecution) -> MlExecution:
        hydrated_artifacts = [self._hydrate_artifact(artifact) for artifact in execution.artifacts]
        return replace(execution, artifacts=hydrated_artifacts)

    def _hydrate_artifact(self, artifact: Artifact) -> Artifact:
        content = self._blob_store.get(artifact.blob_key)
        if content is None:
            raise ArtifactBlobMissing(
                f"blob {artifact.blob_key} for a {artifact.artifact_type.value} "
                "artifact is missing from the blob store"
            )
        return replace(artifact, content=content)

    # -- journal ----------------------------------------------------------

    def _record(
        self, event: str, execution_key: str, command: RunManagedLocalExecutionCommand
    ) -> None:
        self._metrics.record_event(
            event,
            execution_key=execution_key,
            client=command.client,
            model=command.model,
            effort=command.effort,
        )
