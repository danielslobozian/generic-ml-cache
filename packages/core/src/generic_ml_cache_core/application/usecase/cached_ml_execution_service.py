# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CachedMlExecutionService: the shared record-or-replay orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import List, Optional, Protocol, Tuple

from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact, ArtifactType
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.usecase import journal_events
from generic_ml_cache_core.common.checksum import file_content_fingerprint
from generic_ml_cache_core.common.errors import ArtifactBlobMissing, CacheMiss

_TEXT_ENCODING = "utf-8"


class CacheableExecutionCommand(Protocol):
    """What the shared flow needs of any execution command: a cache mode and a
    persistence policy. The kind-specific fields are read through hooks."""

    cache_mode: CacheMode

    def should_persist(self, succeeded: bool) -> bool: ...


class CachedMlExecutionService(ABC):
    """The record-or-replay flow shared by every kind of cached ML execution.

    It owns the cache resolution (offline/cache/refresh), content-addressed
    artifact storage, hydration on a hit, and journaling. Each concrete kind
    supplies only what differs through the hooks below — how to build its
    identity, how to run its client, its kind, and (optionally) whether a given
    command is cacheable. This is where "what happens in what order" lives; the
    kind-specific I/O lives in the subclass.
    """

    def __init__(
        self, blob_store: BlobStorePort, repository: ExecutionRepositoryPort, metrics: MetricsPort
    ) -> None:
        self._blob_store = blob_store
        self._repository = repository
        self._metrics = metrics

    def execute(self, command: CacheableExecutionCommand) -> MlExecution:
        call_identity = self._build_identity(command)
        execution_key = call_identity.generate_key()

        if self._is_uncacheable(command):
            return self._run_uncacheable(command, call_identity, execution_key)

        if command.cache_mode is CacheMode.OFFLINE:
            return self._serve_offline(command, execution_key)

        if command.cache_mode is CacheMode.CACHE:
            current_execution = self._repository.find_current(execution_key)
            if current_execution is not None:
                return self._serve_hit(command, execution_key, current_execution)

        return self._run_fresh(command, call_identity, execution_key, allow_store=True)

    # -- kind-specific hooks ----------------------------------------------

    @abstractmethod
    def _build_identity(self, command: CacheableExecutionCommand) -> CallIdentity:
        """Build the call identity (and thus the key) for this command."""

    @abstractmethod
    def _run_client(self, command: CacheableExecutionCommand) -> ClientRunResult:
        """Run the client for this command and return its raw result."""

    @abstractmethod
    def _execution_kind(self) -> ExecutionKind:
        """The kind every execution this service produces is tagged with."""

    @abstractmethod
    def _journal_fields(self, command: CacheableExecutionCommand) -> Tuple[str, str, str]:
        """The (client, model, effort) a journal event records for this command;
        a kind without a model/effort returns empty strings for them."""

    def _is_uncacheable(self, command: CacheableExecutionCommand) -> bool:
        """Whether this command cannot be cached. Default: always cacheable."""
        return False

    def _execution_tags(self, command: CacheableExecutionCommand) -> List[str]:
        """User-supplied tags to attach to executions this service records.
        Metadata only — never part of the key. Default: none."""
        return []

    def _apply_tags(self, execution_key: str, command: CacheableExecutionCommand) -> None:
        """Attach the command's tags to the current execution for this key,
        idempotently (a no-op when there are none). Tags are a separate
        annotation: adding one never rewrites the execution record."""
        tags = self._execution_tags(command)
        if tags:
            self._repository.add_tags(execution_key, tags)

    # -- resolution paths -------------------------------------------------

    def _serve_offline(self, command: CacheableExecutionCommand, execution_key: str) -> MlExecution:
        current_execution = self._repository.find_current(execution_key)
        if current_execution is None:
            self._record_event(journal_events.MISS, execution_key, command)
            raise CacheMiss(f"offline miss: no stored execution for key {execution_key}")
        return self._serve_hit(command, execution_key, current_execution)

    def _serve_hit(
        self, command: CacheableExecutionCommand, execution_key: str, current_execution: MlExecution
    ) -> MlExecution:
        hydrated_execution = self._hydrate(current_execution)
        self._record_event(journal_events.HIT, execution_key, command)
        self._apply_tags(execution_key, command)
        return hydrated_execution

    def _run_uncacheable(
        self, command: CacheableExecutionCommand, call_identity: CallIdentity, execution_key: str
    ) -> MlExecution:
        if command.cache_mode is CacheMode.OFFLINE:
            self._record_event(journal_events.MISS, execution_key, command)
            raise CacheMiss("offline: this call is not cacheable, so it cannot be served offline")
        return self._run_fresh(command, call_identity, execution_key, allow_store=False)

    def _run_fresh(
        self,
        command: CacheableExecutionCommand,
        call_identity: CallIdentity,
        execution_key: str,
        allow_store: bool,
    ) -> MlExecution:
        client_run_result = self._run_client(command)
        should_store = allow_store and command.should_persist(client_run_result.succeeded)
        artifacts = self._build_artifacts(client_run_result, store=should_store)
        execution = MlExecution(
            call_identity=call_identity,
            execution_state=client_run_result.outcome(),
            execution_kind=self._execution_kind(),
            output_persisted=should_store,
            artifacts=artifacts,
            token_usage=client_run_result.token_usage,
            failure=client_run_result.failure(),
        )
        if should_store:
            self._repository.save(execution)
            self._record_event(journal_events.RECORD, execution_key, command)
            self._apply_tags(execution_key, command)
        else:
            self._record_event(journal_events.RUN, execution_key, command)
        return execution

    # -- artifacts --------------------------------------------------------

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
        self, event: str, execution_key: str, command: CacheableExecutionCommand
    ) -> None:
        client, model, effort = self._journal_fields(command)
        self._metrics.record_event(
            event, execution_key=execution_key, client=client, model=model, effort=effort
        )
