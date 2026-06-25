# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CachedMlExecutionService: the shared record-or-replay orchestration."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import replace
from typing import Dict, Generator, List, Optional, Protocol, Tuple

from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact, ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
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
    persistence_depth: PersistenceDepth
    session_id: Optional[str]

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
        self._key_locks: Dict[str, threading.Lock] = {}
        self._key_locks_guard = threading.Lock()

    def execute(self, command: CacheableExecutionCommand) -> MlExecution:
        call_identity = self._build_identity(command)
        execution_key = call_identity.generate_key()

        if self._is_uncacheable(command):
            return self._run_uncacheable(command, call_identity, execution_key)

        if command.cache_mode is CacheMode.OFFLINE:
            return self._serve_offline(command, execution_key)

        if not command.persistence_depth.stores_output:
            # METER: never replays — always run, store nothing, but record whether
            # the call *would* have hit a stored entry (would-be hit/miss).
            return self._run_metered(command, call_identity, execution_key)

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
    def _execution_kind(self, command: CacheableExecutionCommand) -> ExecutionKind:
        """The execution kind to tag the result with for this command."""

    @abstractmethod
    def _journal_fields(self, command: CacheableExecutionCommand) -> Tuple[str, str, str]:
        """The (client, model, effort) a journal event records for this command;
        a kind without a model/effort returns empty strings for them."""

    def _is_uncacheable(self, command: CacheableExecutionCommand) -> bool:
        """Whether this command cannot be cached. Default: always cacheable."""
        return False

    def _after_record(self, execution_key: str) -> None:
        """Called once after a successful store. Override to add post-record hooks
        such as quota-based eviction. Default: no-op."""

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
        self._accumulate_input(command, execution_key, current_execution)
        return hydrated_execution

    def _accumulate_input(
        self, command: CacheableExecutionCommand, execution_key: str, current_execution: MlExecution
    ) -> None:
        """If the user now wants the input kept (DATASET) and this entry doesn't yet
        carry it, back-fill it onto the existing entry — the input is in the command,
        so no re-run is needed. Mirrors how tags accumulate on a hit; the user
        changing their mind to enrich the stored data is their decision."""
        if not command.persistence_depth.stores_input or current_execution.input_persisted:
            return
        input_artifacts = self._build_input_artifacts(command, store=True)
        if input_artifacts:
            self._repository.add_input_artifacts(execution_key, input_artifacts)

    def _run_uncacheable(
        self, command: CacheableExecutionCommand, call_identity: CallIdentity, execution_key: str
    ) -> MlExecution:
        if command.cache_mode is CacheMode.OFFLINE:
            self._record_event(journal_events.MISS, execution_key, command)
            raise CacheMiss("offline: this call is not cacheable, so it cannot be served offline")
        return self._run_fresh(command, call_identity, execution_key, allow_store=False)

    @contextmanager
    def _acquire_key_lock(self, execution_key: str) -> Generator[None, None, None]:
        """Yield with a per-key lock held, creating it on first use."""
        with self._key_locks_guard:
            if execution_key not in self._key_locks:
                self._key_locks[execution_key] = threading.Lock()
            lock = self._key_locks[execution_key]
        with lock:
            yield

    def _run_fresh(
        self,
        command: CacheableExecutionCommand,
        call_identity: CallIdentity,
        execution_key: str,
        allow_store: bool,
    ) -> MlExecution:
        if allow_store:
            return self._run_fresh_locked(command, call_identity, execution_key)
        # Uncacheable: no lock, no IN_PROGRESS, no repository write.
        client_run_result = self._run_client(command)
        artifacts = self._build_artifacts(client_run_result, store=False)
        execution = MlExecution(
            call_identity=call_identity,
            execution_state=client_run_result.outcome(),
            execution_kind=self._execution_kind(command),
            output_persisted=False,
            input_persisted=False,
            artifacts=artifacts,
            token_usage=client_run_result.token_usage,
            failure=client_run_result.failure(),
        )
        self._record_event(journal_events.RUN, execution_key, command)
        return execution

    def _run_fresh_locked(
        self,
        command: CacheableExecutionCommand,
        call_identity: CallIdentity,
        execution_key: str,
    ) -> MlExecution:
        """Run the client under a per-key lock, bookending the call with
        IN_PROGRESS and the final execution record in the repository."""
        with self._acquire_key_lock(execution_key):
            # Another thread holding this lock may have just completed this key.
            if command.cache_mode is CacheMode.CACHE:
                current = self._repository.find_current(execution_key)
                if current is not None:
                    return self._serve_hit(command, execution_key, current)

            # Write the IN_PROGRESS marker before the client is called so that
            # external observers (dashboard, probe, inspector) can see the run.
            self._repository.save(
                MlExecution(
                    call_identity=call_identity,
                    execution_state=ExecutionState.IN_PROGRESS,
                    execution_kind=self._execution_kind(command),
                    output_persisted=False,
                    input_persisted=False,
                    artifacts=[],
                )
            )

            client_run_result = self._run_client(command)
            should_store = command.should_persist(client_run_result.succeeded)
            artifacts = self._build_artifacts(client_run_result, store=should_store)
            # Input rides on a stored output (DATASET is a superset of CACHE).
            store_input = should_store and command.persistence_depth.stores_input
            input_artifacts = self._build_input_artifacts(command, store=store_input)
            execution = MlExecution(
                call_identity=call_identity,
                execution_state=client_run_result.outcome(),
                execution_kind=self._execution_kind(command),
                output_persisted=should_store,
                input_persisted=bool(input_artifacts),
                artifacts=artifacts + input_artifacts,
                token_usage=client_run_result.token_usage,
                failure=client_run_result.failure(),
            )
            # Always resolve the IN_PROGRESS record with the final execution.
            self._repository.save(execution)
            if should_store:
                self._record_event(journal_events.RECORD, execution_key, command)
                self._apply_tags(execution_key, command)
                self._after_record(execution_key)
            else:
                self._record_event(journal_events.RUN, execution_key, command)
            return execution

    def _run_metered(
        self, command: CacheableExecutionCommand, call_identity: CallIdentity, execution_key: str
    ) -> MlExecution:
        """METER depth: always run and store nothing, but journal whether a stored
        entry existed — so usage analytics can report would-be hit/miss ("you'd
        have saved N runs") without the cache ever serving or storing anything."""
        would_hit = self._repository.find_current(execution_key) is not None
        client_run_result = self._run_client(command)
        execution = MlExecution(
            call_identity=call_identity,
            execution_state=client_run_result.outcome(),
            execution_kind=self._execution_kind(command),
            output_persisted=False,
            input_persisted=False,
            artifacts=self._build_artifacts(client_run_result, store=False),
            token_usage=client_run_result.token_usage,
            failure=client_run_result.failure(),
        )
        event = journal_events.WOULD_HIT if would_hit else journal_events.WOULD_MISS
        self._record_event(event, execution_key, command)
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

    def _build_input_artifacts(
        self, command: CacheableExecutionCommand, store: bool
    ) -> List[Artifact]:
        """The input documents to keep at DATASET depth, content-addressed like
        any artifact. Empty when ``store`` is false (below DATASET, or nothing was
        stored) or when the kind has no recordable input."""
        if not store:
            return []
        return [
            self._store_artifact(artifact_type, name, content_bytes, store=True)
            for (artifact_type, name, content_bytes) in self._input_parts(command)
        ]

    def _input_parts(
        self, command: CacheableExecutionCommand
    ) -> List[Tuple[ArtifactType, Optional[str], bytes]]:
        """The ``(type, name, bytes)`` input documents this kind would persist at
        DATASET depth. Default: none — a kind whose input is not recorded."""
        return []

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
            event,
            execution_key=execution_key,
            client=client,
            model=model,
            effort=effort,
            session_id=command.session_id,
        )
