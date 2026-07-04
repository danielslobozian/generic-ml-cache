# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CachedMlExecutionService: the shared record-or-replay orchestration."""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import replace
from typing import Generic, Protocol, TypeVar

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
from generic_ml_cache_core.application.domain.model.execution.execution_id import ExecutionId
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.call_journal_ports import RecordCallEventPort
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.ml_run_ports import (
    AnnotateMlRunPort,
    ReadMlRunPort,
    SaveMlRunPort,
)
from generic_ml_cache_core.common import journal_events
from generic_ml_cache_core.common.checksum import file_content_fingerprint
from generic_ml_cache_core.common.errors import ArtifactBlobMissing, CacheMiss

_TEXT_ENCODING = "utf-8"
_EXECUTE_EXIT = "execute EXIT"

#: Number of stripes in the per-key lock array. A fixed pool bounds memory forever
#: (W29): a key hashes to one stripe, so two distinct keys occasionally share a lock
#: and one waits briefly — harmless, and cheaper than a lock-per-key dict that grows
#: without bound for a long-lived daemon. The in-process lock only stops same-process
#: duplicate work; cross-process correctness is the database's job (W1).
_KEY_LOCK_STRIPE_COUNT = 64


class CacheableExecutionCommand(Protocol):
    """What the shared flow needs of any execution command: a cache mode and a
    persistence policy. The kind-specific fields are read through hooks.

    Attributes are declared read-only (@property) so frozen dataclasses satisfy
    this protocol without pyright mutable-attribute mismatches.
    """

    @property
    def cache_mode(self) -> CacheMode: ...
    @property
    def persistence_depth(self) -> PersistenceDepth: ...
    @property
    def session_id(self) -> str | None: ...

    def should_persist(self, succeeded: bool) -> bool: ...


# The concrete command type a subclass handles. Bound to the protocol so the
# shared flow can rely on cache_mode/persistence_depth/etc., while each subclass
# binds the exact command (e.g. RunMlExecutionCommand) — making the hook
# overrides that narrow to that command type sound (no Liskov violation).
TCommand = TypeVar("TCommand", bound="CacheableExecutionCommand")


class CachedMlExecutionService(ABC, Generic[TCommand]):
    """The record-or-replay flow shared by every kind of cached ML execution.

    It owns the cache resolution (offline/cache/refresh), content-addressed
    artifact storage, hydration on a hit, and journaling. Each concrete kind
    supplies only what differs through the hooks below — how to build its
    identity, how to run its client, its kind, and (optionally) whether a given
    command is cacheable. This is where "what happens in what order" lives; the
    kind-specific I/O lives in the subclass.
    """

    def __init__(
        self,
        blob_store: BlobStorePort,
        save: SaveMlRunPort,
        read: ReadMlRunPort,
        annotate: AnnotateMlRunPort,
        record: RecordCallEventPort,
        diag: DiagnosticsPort | None = None,
    ) -> None:
        self._blob_store = blob_store
        self._save = save
        self._read = read
        self._annotate = annotate
        self._record = record
        self._diag: DiagnosticsPort | None = diag
        # A fixed pool of striped locks (W29): bounded memory, no per-key growth.
        self._key_lock_stripes = tuple(threading.Lock() for _ in range(_KEY_LOCK_STRIPE_COUNT))

    def execute(self, command: TCommand) -> MlExecution:  # noqa: C901
        _t = time.perf_counter()
        call_identity = self._build_identity(command)
        execution_key = call_identity.generate_key()

        if self._diag:
            self._diag.debug("execute ENTER", key=execution_key, mode=command.cache_mode.value)

        try:
            if self._is_uncacheable(command):
                if self._diag:
                    self._diag.debug("uncacheable — bypassing cache", key=execution_key)
                result = self._run_uncacheable(command, call_identity, execution_key)
                if self._diag:
                    self._diag.debug(
                        _EXECUTE_EXIT,
                        key=execution_key,
                        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                        outcome="uncacheable",
                    )
                return result

            if command.cache_mode is CacheMode.OFFLINE:
                result = self._serve_offline(command, execution_key)
                if self._diag:
                    self._diag.debug(
                        _EXECUTE_EXIT,
                        key=execution_key,
                        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                        outcome="offline-hit",
                    )
                return result

            if not command.persistence_depth.stores_output:
                # METER: never replays — always run, store nothing, but record whether
                # the call *would* have hit a stored entry (would-be hit/miss).
                result = self._run_metered(command, call_identity, execution_key)
                if self._diag:
                    self._diag.debug(
                        _EXECUTE_EXIT,
                        key=execution_key,
                        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                        outcome="metered",
                    )
                return result

            if command.cache_mode is CacheMode.CACHE:
                current_execution = self._read.find_current(execution_key)
                if current_execution is not None:
                    result = self._serve_hit(command, execution_key, current_execution)
                    if self._diag:
                        self._diag.debug(
                            _EXECUTE_EXIT,
                            key=execution_key,
                            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                            outcome="hit",
                        )
                    return result

            result = self._run_fresh(command, call_identity, execution_key, allow_store=True)
            if self._diag:
                self._diag.debug(
                    "execute EXIT",
                    key=execution_key,
                    duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                    outcome="fresh-run",
                )
            return result
        except CacheMiss:
            if self._diag:
                self._diag.debug(
                    "execute EXIT — cache-miss",
                    key=execution_key,
                    duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                )
            raise
        except Exception as exc:
            if self._diag:
                self._diag.error(
                    "execute FAILED",
                    key=execution_key,
                    duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                    exc=exc,
                )
            raise

    # -- kind-specific hooks ----------------------------------------------

    @abstractmethod
    def _build_identity(self, command: TCommand) -> CallIdentity:
        """Build the call identity (and thus the key) for this command."""

    @abstractmethod
    def _run_client(self, command: TCommand) -> ClientRunResult:
        """Run the client for this command and return its raw result."""

    @abstractmethod
    def _execution_kind(self, command: TCommand) -> ExecutionKind:
        """The execution kind to tag the result with for this command."""

    @abstractmethod
    def _journal_fields(self, command: TCommand) -> tuple[str, str, str]:
        """The (client, model, effort) a journal event records for this command;
        a kind without a model/effort returns empty strings for them."""

    def _is_uncacheable(self, command: TCommand) -> bool:
        """Whether this command cannot be cached. Default: always cacheable."""
        return False

    def _after_record(self, execution_key: str) -> None:
        """Called once after a successful store. Override to add post-record hooks
        such as quota-based eviction. Default: no-op."""

    def _execution_tags(self, command: TCommand) -> list[str]:
        """User-supplied tags to attach to executions this service records.
        Metadata only — never part of the key. Default: none."""
        return []

    def _apply_tags(self, execution_key: str, command: TCommand) -> None:
        """Attach the command's tags to the current execution for this key,
        idempotently (a no-op when there are none). Tags are a separate
        annotation: adding one never rewrites the execution record."""
        tags = self._execution_tags(command)
        if tags:
            self._annotate.add_tags(execution_key, tags)

    # -- resolution paths -------------------------------------------------

    def _serve_offline(self, command: TCommand, execution_key: str) -> MlExecution:
        _t = time.perf_counter()
        if self._diag:
            self._diag.debug("serve-offline ENTER", key=execution_key)
        current_execution = self._read.find_current(execution_key)
        if current_execution is None:
            if self._diag:
                self._diag.warn(
                    "offline miss — no stored execution",
                    key=execution_key,
                    duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                )
            self._record_event(journal_events.MISS, execution_key, command)
            raise CacheMiss(f"offline miss: no stored execution for key {execution_key}")
        result = self._serve_hit(command, execution_key, current_execution)
        if self._diag:
            self._diag.debug(
                "serve-offline EXIT",
                key=execution_key,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return result

    def _serve_hit(
        self, command: TCommand, execution_key: str, current_execution: MlExecution
    ) -> MlExecution:
        _t = time.perf_counter()
        if self._diag:
            self._diag.info("cache HIT", key=execution_key)
        hydrated_execution = self._hydrate(current_execution)
        self._record_event(journal_events.HIT, execution_key, command)
        self._apply_tags(execution_key, command)
        self._accumulate_input(command, execution_key, current_execution)
        if self._diag:
            self._diag.debug(
                "serve-hit EXIT",
                key=execution_key,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return hydrated_execution

    def _accumulate_input(
        self, command: TCommand, execution_key: str, current_execution: MlExecution
    ) -> None:
        """If the user now wants the input kept (DATASET) and this entry doesn't yet
        carry it, back-fill it onto the existing entry — the input is in the command,
        so no re-run is needed. Mirrors how tags accumulate on a hit; the user
        changing their mind to enrich the stored data is their decision."""
        if not command.persistence_depth.stores_input or current_execution.input_persisted:
            return
        input_artifacts = self._build_input_artifacts(command, status=ArtifactStatus.PENDING)
        if input_artifacts:
            # DB-first: attach the PENDING rows to the current execution, then store
            # each blob and flip to STORED/FAILED — no orphaned back-filled blobs.
            # mark/finalize target the current execution's own execution_id.
            self._annotate.add_input_artifacts(execution_key, input_artifacts)
            for artifact in input_artifacts:
                self._store_blob(current_execution.execution_id, artifact)

    def _run_uncacheable(
        self, command: TCommand, call_identity: CallIdentity, execution_key: str
    ) -> MlExecution:
        if command.cache_mode is CacheMode.OFFLINE:
            self._record_event(journal_events.MISS, execution_key, command)
            raise CacheMiss("offline: this call is not cacheable, so it cannot be served offline")
        return self._run_fresh(command, call_identity, execution_key, allow_store=False)

    def _lock_for_key(self, execution_key: str) -> threading.Lock:
        """The striped lock guarding this key. ``hash`` is per-process (fine — the
        lock is intra-process only), and Python's ``%`` keeps the index in range."""
        return self._key_lock_stripes[hash(execution_key) % _KEY_LOCK_STRIPE_COUNT]

    @contextmanager
    def _acquire_key_lock(self, execution_key: str) -> Generator[None, None, None]:
        """Yield with the key's striped lock held."""
        with self._lock_for_key(execution_key):
            yield

    def _run_fresh(
        self,
        command: TCommand,
        call_identity: CallIdentity,
        execution_key: str,
        allow_store: bool,
    ) -> MlExecution:
        if allow_store:
            return self._run_fresh_locked(command, call_identity, execution_key)
        # Uncacheable: no lock, no IN_PROGRESS, no repository write.
        client_run_result = self._run_client(command)
        artifacts = self._build_artifacts(client_run_result)
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
        command: TCommand,
        call_identity: CallIdentity,
        execution_key: str,
    ) -> MlExecution:
        """Run the client under a per-key lock, bookending the call with
        IN_PROGRESS and the final execution record in the repository."""
        _t = time.perf_counter()
        if self._diag:
            self._diag.debug("run-fresh-locked ENTER", key=execution_key)
        with self._acquire_key_lock(execution_key):
            # Another thread holding this lock may have just completed this key.
            if command.cache_mode is CacheMode.CACHE:
                current = self._read.find_current(execution_key)
                if current is not None:
                    result = self._serve_hit(command, execution_key, current)
                    if self._diag:
                        self._diag.debug(
                            "run-fresh-locked EXIT",
                            key=execution_key,
                            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                            stored=False,
                        )
                    return result

            # Insert the IN_PROGRESS row before the client is called so external
            # observers (dashboard, probe, inspector) can see the in-flight run.
            # This is the ONE row for this call: record_outcome / mark / finalize
            # update it in place, targeting its execution_id — never a second
            # insert whose "latest row by key" a concurrent writer could steal (W1).
            in_progress = MlExecution(
                call_identity=call_identity,
                execution_state=ExecutionState.IN_PROGRESS,
                execution_kind=self._execution_kind(command),
                output_persisted=False,
                input_persisted=False,
                artifacts=[],
            )
            self._save.save(in_progress)

            if self._diag:
                self._diag.info("cache MISS — running client", key=execution_key)
            client_run_result = self._run_client(command)
            should_store = command.should_persist(client_run_result.succeeded)
            if not should_store:
                return self._record_unstored(
                    command, in_progress, execution_key, client_run_result, _t
                )
            return self._record_stored(command, in_progress, execution_key, client_run_result, _t)

    def _record_unstored(
        self,
        command: TCommand,
        in_progress: MlExecution,
        execution_key: str,
        client_run_result: ClientRunResult,
        _t: float,
    ) -> MlExecution:
        """A run that is not persisted (a failure without ``record_on_error``):
        transition the IN_PROGRESS row to its final outcome with NO artifact rows
        (they would be unhydratable noise), but return the artifacts hydrated so the
        caller can show the client's output."""
        execution = replace(
            in_progress,
            execution_state=client_run_result.outcome(),
            token_usage=client_run_result.token_usage,
            failure=client_run_result.failure(),
        )
        self._save.record_outcome(execution)
        if self._diag:
            self._diag.info(
                "client run complete — not stored",
                key=execution_key,
                succeeded=client_run_result.succeeded,
            )
        self._record_event(journal_events.RUN, execution_key, command)
        if self._diag:
            self._diag.debug(
                "run-fresh-locked EXIT",
                key=execution_key,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                stored=False,
            )
        return replace(execution, artifacts=self._build_artifacts(client_run_result))

    def _record_stored(
        self,
        command: TCommand,
        in_progress: MlExecution,
        execution_key: str,
        client_run_result: ClientRunResult,
        _t: float,
    ) -> MlExecution:
        """DB-first store: transition the IN_PROGRESS row to its outcome, then persist
        each document one at a time (insert PENDING → link an already-stored blob or
        write it → mark STORED/FAILED), and finally ``finalize`` (supersede + persist)
        only when every artifact is STORED. A blob-write failure leaves the run
        recorded but not servable, with the failed artifacts visible to re-run."""
        execution = replace(
            in_progress,
            execution_state=client_run_result.outcome(),
            token_usage=client_run_result.token_usage,
            failure=client_run_result.failure(),
        )
        self._save.record_outcome(execution)
        output_artifacts = self._build_artifacts(client_run_result, status=ArtifactStatus.PENDING)
        # Input rides on a stored output (DATASET is a superset of CACHE).
        store_input = command.persistence_depth.stores_input
        input_artifacts = (
            self._build_input_artifacts(command, status=ArtifactStatus.PENDING)
            if store_input
            else []
        )
        resolved, all_stored = self._persist_documents(
            execution.execution_id, output_artifacts + input_artifacts
        )
        if all_stored:
            self._save.finalize_output_persisted(execution.execution_id)
            if self._diag:
                self._diag.info("cached RECORD", key=execution_key)
            self._record_event(journal_events.RECORD, execution_key, command)
            self._apply_tags(execution_key, command)
            self._after_record(execution_key)
        else:
            if self._diag:
                self._diag.warn(
                    "artifact persistence incomplete — run not cached", key=execution_key
                )
            self._record_event(journal_events.RUN, execution_key, command)
        if self._diag:
            self._diag.debug(
                "run-fresh-locked EXIT",
                key=execution_key,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                stored=all_stored,
            )
        return replace(
            execution,
            output_persisted=all_stored,
            input_persisted=bool(input_artifacts),
            artifacts=resolved,
        )

    def _run_metered(
        self, command: TCommand, call_identity: CallIdentity, execution_key: str
    ) -> MlExecution:
        """METER depth: always run and store nothing, but journal whether a stored
        entry existed — so usage analytics can report would-be hit/miss ("you'd
        have saved N runs") without the cache ever serving or storing anything."""
        _t = time.perf_counter()
        would_hit = self._read.find_current(execution_key) is not None
        if self._diag:
            self._diag.debug("METER run", key=execution_key, would_hit=would_hit)
        client_run_result = self._run_client(command)
        execution = MlExecution(
            call_identity=call_identity,
            execution_state=client_run_result.outcome(),
            execution_kind=self._execution_kind(command),
            output_persisted=False,
            input_persisted=False,
            artifacts=self._build_artifacts(client_run_result),
            token_usage=client_run_result.token_usage,
            failure=client_run_result.failure(),
        )
        event = journal_events.WOULD_HIT if would_hit else journal_events.WOULD_MISS
        self._record_event(event, execution_key, command)
        if self._diag:
            self._diag.debug(
                "METER run EXIT",
                key=execution_key,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                would_hit=would_hit,
            )
        return execution

    # -- artifacts --------------------------------------------------------

    def _build_artifacts(
        self, client_run_result: ClientRunResult, status: ArtifactStatus = ArtifactStatus.STORED
    ) -> list[Artifact]:
        """Build the output artifacts (content-addressed, hydrated), WITHOUT writing
        any blob. ``status`` is ``PENDING`` on the DB-first store path (the blob is
        put afterwards by ``_persist_artifact_blobs``) and defaults to ``STORED`` for
        display-only artifacts on the non-persisted paths."""
        artifacts = [
            self._make_artifact(
                ArtifactType.STDOUT, None, client_run_result.stdout.encode(_TEXT_ENCODING), status
            ),
            self._make_artifact(
                ArtifactType.STDERR, None, client_run_result.stderr.encode(_TEXT_ENCODING), status
            ),
        ]
        for generated_file in client_run_result.files:
            artifacts.append(
                self._make_artifact(
                    ArtifactType.OUTPUT_FILE, generated_file.name, generated_file.content, status
                )
            )
        return artifacts

    @staticmethod
    def _make_artifact(
        artifact_type: ArtifactType,
        artifact_name: str | None,
        content_bytes: bytes,
        status: ArtifactStatus,
    ) -> Artifact:
        blob_key = BlobKey(file_content_fingerprint(content_bytes))
        return Artifact.from_content(
            artifact_type, blob_key, content_bytes, name=artifact_name, status=status
        )

    def _persist_documents(
        self, execution_id: ExecutionId, artifacts: list[Artifact]
    ) -> tuple[list[Artifact], bool]:
        """Persist each document one at a time against ``execution_id`` (the W1
        per-document path): insert its PENDING row, then store its blob and resolve
        the row to STORED/FAILED. Returns the artifacts with their resolved status
        and whether every one is STORED."""
        resolved: list[Artifact] = []
        all_stored = True
        for artifact in artifacts:
            self._save.persist_artifact(execution_id, artifact)
            stored_artifact = self._store_blob(execution_id, artifact)
            resolved.append(stored_artifact)
            if stored_artifact.status is ArtifactStatus.FAILED:
                all_stored = False
        return resolved, all_stored

    def _store_blob(self, execution_id: ExecutionId, artifact: Artifact) -> Artifact:
        """Link an already-stored content-addressed blob (no rewrite) or write it,
        then mark the artifact STORED; a write failure marks it FAILED with the
        detail — caught and surfaced, never thrown out of execute() (§10)."""
        if self._blob_store.exists(artifact.blob_key):
            self._save.mark_artifacts_stored(execution_id, artifact.blob_key)
            return replace(artifact, status=ArtifactStatus.STORED)
        try:
            self._blob_store.put(artifact.blob_key, artifact.content or b"")
            self._save.mark_artifacts_stored(execution_id, artifact.blob_key)
            return replace(artifact, status=ArtifactStatus.STORED)
        except Exception as exc:  # noqa: BLE001 — translate ANY blob-write failure to a visible FAILED status (§10)
            self._save.mark_artifacts_failed(execution_id, artifact.blob_key, str(exc))
            if self._diag:
                self._diag.error(
                    "artifact blob write failed",
                    execution_id=execution_id,
                    blob=artifact.blob_key,
                    exc=exc,
                )
            return replace(artifact, status=ArtifactStatus.FAILED, status_detail=str(exc))

    def _build_input_artifacts(
        self, command: TCommand, status: ArtifactStatus = ArtifactStatus.STORED
    ) -> list[Artifact]:
        """The input documents to keep at DATASET depth, content-addressed like any
        artifact (no blob written here — the caller stores them DB-first). Empty when
        the kind has no recordable input."""
        return [
            self._make_artifact(artifact_type, name, content_bytes, status)
            for (artifact_type, name, content_bytes) in self._input_parts(command)
        ]

    def _input_parts(self, command: TCommand) -> list[tuple[ArtifactType, str | None, bytes]]:
        """The ``(type, name, bytes)`` input documents this kind would persist at
        DATASET depth. Default: none — a kind whose input is not recorded."""
        return []

    def _hydrate(self, execution: MlExecution) -> MlExecution:
        hydrated_artifacts = [self._hydrate_artifact(artifact) for artifact in execution.artifacts]
        return replace(execution, artifacts=hydrated_artifacts)

    def _hydrate_artifact(self, artifact: Artifact) -> Artifact:
        content_bytes = self._blob_store.get(artifact.blob_key)
        if content_bytes is None:
            if self._diag:
                self._diag.error(
                    "blob missing — artifact cannot be hydrated",
                    blob_key=artifact.blob_key,
                    artifact_type=artifact.artifact_type.value,
                )
            raise ArtifactBlobMissing(
                f"blob {artifact.blob_key} for a {artifact.artifact_type.value} "
                "artifact is missing from the blob store"
            )
        return replace(artifact, content=content_bytes)

    # -- journal ----------------------------------------------------------

    def _record_event(self, event: str, execution_key: str, command: TCommand) -> None:
        client, model, effort = self._journal_fields(command)
        self._record.record_event(
            event,
            execution_key=execution_key,
            client=client,
            model=model,
            effort=effort,
            session_id=command.session_id,
        )
