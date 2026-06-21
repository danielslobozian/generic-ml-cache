# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunManagedLocalExecutionUseCase."""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional

from generic_ml_cache.application.domain.model.artifact import Artifact, ArtifactType
from generic_ml_cache.application.domain.model.cache_mode import CacheMode
from generic_ml_cache.application.domain.model.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.client_run_request import ClientRunRequest
from generic_ml_cache.application.domain.model.client_run_result import ClientRunResult
from generic_ml_cache.application.domain.model.execution_kind import ExecutionKind
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
from generic_ml_cache.common.checksum import (
    file_content_fingerprint,
    fingerprint_arguments,
    text_checksum,
)
from generic_ml_cache.common.errors import ArtifactBlobMissing, CacheMiss

_TEXT_ENCODING = "utf-8"


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

        if command.is_uncacheable:
            return self._run_uncacheable(command, call_identity, execution_key)

        if command.cache_mode is CacheMode.OFFLINE:
            return self._serve_offline(command, execution_key)

        if command.cache_mode is CacheMode.CACHE:
            current_execution = self._repository.find_current(execution_key)
            if current_execution is not None:
                return self._serve_hit(command, execution_key, current_execution)

        return self._run_fresh(command, call_identity, execution_key, allow_store=True)

    # -- identity ---------------------------------------------------------

    def _build_call_identity(self, command: RunManagedLocalExecutionCommand) -> CallIdentity:
        input_file_fingerprints = {
            input_file_path: self._file_fingerprint.fingerprint(input_file_path)
            for input_file_path in command.input_file_paths
        }
        client_args_fingerprint = (
            fingerprint_arguments(command.client_args) if command.client_args else None
        )
        return CallIdentity(
            client=command.client,
            model=command.model,
            effort=command.effort,
            context_fingerprint=text_checksum(command.context),
            prompt_fingerprint=text_checksum(command.prompt),
            input_file_fingerprints=input_file_fingerprints,
            client_args_fingerprint=client_args_fingerprint,
            grants=frozenset(command.grants),
        )

    # -- resolution paths -------------------------------------------------

    def _serve_offline(
        self, command: RunManagedLocalExecutionCommand, execution_key: str
    ) -> MlExecution:
        current_execution = self._repository.find_current(execution_key)
        if current_execution is None:
            self._record_event(journal_events.MISS, execution_key, command)
            raise CacheMiss(f"offline miss: no stored execution for key {execution_key}")
        return self._serve_hit(command, execution_key, current_execution)

    def _serve_hit(
        self,
        command: RunManagedLocalExecutionCommand,
        execution_key: str,
        current_execution: MlExecution,
    ) -> MlExecution:
        hydrated_execution = self._hydrate(current_execution)
        self._record_event(journal_events.HIT, execution_key, command)
        return hydrated_execution

    def _run_uncacheable(
        self,
        command: RunManagedLocalExecutionCommand,
        call_identity: CallIdentity,
        execution_key: str,
    ) -> MlExecution:
        if command.cache_mode is CacheMode.OFFLINE:
            self._record_event(journal_events.MISS, execution_key, command)
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
        client_run_result = self._client_runner.run(self._build_client_run_request(command))
        should_store = allow_store and command.should_persist(client_run_result.succeeded)
        artifacts = self._build_artifacts(client_run_result, store=should_store)
        execution = MlExecution(
            call_identity=call_identity,
            execution_state=client_run_result.outcome(),
            execution_kind=ExecutionKind.LOCAL_MANAGED,
            output_persisted=should_store,
            artifacts=artifacts,
            failure=client_run_result.failure(),
        )
        if should_store:
            self._repository.save(execution)
            self._record_event(journal_events.RECORD, execution_key, command)
        else:
            self._record_event(journal_events.RUN, execution_key, command)
        return execution

    # -- client run -------------------------------------------------------

    @staticmethod
    def _build_client_run_request(command: RunManagedLocalExecutionCommand) -> ClientRunRequest:
        # The one allowed self-less method (AGENTS §6): the inbound-command ->
        # outbound-port-DTO boundary mapping, which is the use case's own job.
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

    # -- artifacts (store) ------------------------------------------------

    def _build_artifacts(self, client_run_result: ClientRunResult, store: bool) -> List[Artifact]:
        artifacts = [
            self._store_artifact(
                ArtifactType.STDOUT, None, client_run_result.stdout.encode(_TEXT_ENCODING), store
            ),
            self._store_artifact(
                ArtifactType.STDERR, None, client_run_result.stderr.encode(_TEXT_ENCODING), store
            ),
        ]
        for generated_file in client_run_result.files:
            artifacts.append(
                self._store_artifact(
                    ArtifactType.OUTPUT_FILE, generated_file.name, generated_file.content, store
                )
            )
        return artifacts

    def _store_artifact(
        self,
        artifact_type: ArtifactType,
        artifact_name: Optional[str],
        content_bytes: bytes,
        store: bool,
    ) -> Artifact:
        blob_key = file_content_fingerprint(content_bytes)
        if store:
            self._blob_store.put(blob_key, content_bytes)
        return Artifact.from_content(artifact_type, blob_key, content_bytes, name=artifact_name)

    # -- artifacts (hydrate) ----------------------------------------------

    def _hydrate(self, execution: MlExecution) -> MlExecution:
        hydrated_artifacts = [self._hydrate_artifact(artifact) for artifact in execution.artifacts]
        return replace(execution, artifacts=hydrated_artifacts)

    def _hydrate_artifact(self, artifact: Artifact) -> Artifact:
        content_bytes = self._blob_store.get(artifact.blob_key)
        if content_bytes is None:
            raise ArtifactBlobMissing(
                f"blob {artifact.blob_key} for a {artifact.artifact_type.value} "
                "artifact is missing from the blob store"
            )
        return replace(artifact, content=content_bytes)

    # -- journal ----------------------------------------------------------

    def _record_event(
        self, event: str, execution_key: str, command: RunManagedLocalExecutionCommand
    ) -> None:
        self._metrics.record_event(
            event,
            execution_key=execution_key,
            client=command.client,
            model=command.model,
            effort=command.effort,
        )
