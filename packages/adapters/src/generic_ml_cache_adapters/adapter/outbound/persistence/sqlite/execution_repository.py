# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SqliteExecutionRepository: the durable, append-only execution store (SQLite)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    INPUT_ARTIFACT_TYPES,
    Artifact,
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache_core.application.domain.model.execution.execution_id import ExecutionId
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.outbound.clock_port import ClockPort
from generic_ml_cache_core.application.port.outbound.ml_run_ports import (
    AnnotateMlRunPort,
    ExecutionSizeEntry,
    ExecutionSummary,
    InspectMlRunsPort,
    PurgeMlRunsPort,
    ReadMlRunPort,
    SaveMlRunPort,
)
from generic_ml_cache_core.application.port.outbound.repair_ml_runs_port import (
    RepairMlRunsPort,
    UnpersistedRun,
)
from generic_ml_cache_core.common.errors import (
    StoreConsistencyError,
    StoreCorrupt,
    StoreLocked,
    StoreUnavailable,
)
from generic_ml_cache_core.common.immutable import thaw

from generic_ml_cache_adapters.adapter.outbound.persistence.call_identity_serialization import (
    SerializedIdentity,
    deserialize_identity,
    serialize_identity,
)
from generic_ml_cache_adapters.db import DbConnection

#: stored string values of the input artifact types, for the idempotency check.
_INPUT_TYPE_VALUES = tuple(t.value for t in INPUT_ARTIFACT_TYPES)


def _require_artifact_update(rowcount: int, execution_id: str, blob_key: BlobKey) -> None:
    """A mark_* that updated zero rows means the artifact it was meant to resolve
    is not there — a stale/mistargeted write. Fail loud rather than no-op (W1)."""
    if rowcount == 0:
        raise StoreConsistencyError(
            f"no artifact row for execution {execution_id} / blob {blob_key} to update"
        )


def _raise_translated(exc: BaseException) -> None:
    """Translate a raw ``sqlite3`` error at the persistence-adapter boundary into the
    project's own vocabulary (§10, X1), keeping the original as ``__cause__``: a
    locked store → :class:`StoreLocked` (transient contention, S2a); a malformed /
    unreadable database image → :class:`StoreCorrupt` (self-heals on the serve path,
    S4); an integrity-constraint violation → :class:`StoreConsistencyError`; any other
    driver error → :class:`StoreUnavailable` (hard outage, S2b). A non-``sqlite3``
    exception — an already-translated :class:`CacheError`, a ``KeyboardInterrupt`` — is
    left untouched, so the caller re-raises it unchanged. This is the W19/``_http.py``
    discipline the provider adapters already follow, extended to the persistence
    adapter so ``import-linter`` (which sees import edges, not exception propagation)
    can no longer miss a raw ``sqlite3`` type crossing the port."""
    if isinstance(exc, sqlite3.IntegrityError):
        raise StoreConsistencyError(f"store integrity violation: {exc}") from exc
    if isinstance(exc, sqlite3.OperationalError):
        if "locked" in str(exc).lower():
            raise StoreLocked(f"cache database is locked: {exc}") from exc
        raise StoreUnavailable(f"cache database operation failed: {exc}") from exc
    if isinstance(exc, sqlite3.DatabaseError):
        raise StoreCorrupt(f"cache database image is malformed: {exc}") from exc
    if isinstance(exc, sqlite3.Error):
        raise StoreUnavailable(f"cache database error: {exc}") from exc


#: One ``executions`` row, in ``_EXECUTION_COLUMNS`` order. ``failure_message``
#: is NULL exactly when ``failure_reason`` is (they are written together from one
#: ``ExecutionFailure``) — a correlation the type system cannot express, so it
#: stays ``Any`` and is only read behind the ``failure_reason`` guard.
_ExecutionRow = tuple[int, str, str, str, int, str | None, str | None, Any, int | None, str | None]


class SqliteExecutionRepository(
    SaveMlRunPort,
    ReadMlRunPort,
    AnnotateMlRunPort,
    InspectMlRunsPort,
    PurgeMlRunsPort,
    RepairMlRunsPort,
):
    """A durable, append-only execution store backed by SQLite.

    Not a portability layer: the SQL is SQLite-dialect (``INTEGER PRIMARY KEY``,
    ``INSERT OR IGNORE``, ``lastrowid``, ``?`` placeholders). The ``DbConnection``
    protocol is the injection seam (core forbids importing a driver; tests inject a
    fake), but the SQL written against it is SQLite-specific by design — portability
    is achieved by implementing the port, not by swapping the connection.

    The hybrid identity persistence (domain-model §3): the queryable fields are
    real columns; the divergent identity fields ride in a JSON column. Executions
    are append-only — many per key — and a servable success atomically supersedes
    the prior current one inside a single transaction. The store holds structure
    only; artifact bytes live in the blob store, so reconstructed artifacts are
    dehydrated (content is None). The clock is injected and stamps supersession.
    """

    def __init__(self, conn_factory: Callable[[], DbConnection], clock: ClockPort) -> None:
        self._conn_factory = conn_factory
        self._clock = clock

    def _connect(self) -> DbConnection:
        return self._conn_factory()

    @contextmanager
    def _write_transaction(self) -> Generator[DbConnection]:
        """A write connection scoped to one transaction: commit on success, roll
        back on any error, always close. Makes the rollback explicit rather than
        leaning on a driver's close-time auto-rollback — the ``DbConnection`` seam
        is DB-API-shaped, and another engine need not roll back on close. A raw
        ``sqlite3`` error is translated to the project's vocabulary at this boundary
        (X1) after the rollback, so no driver type crosses the port."""
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except BaseException as exc:
            connection.rollback()
            _raise_translated(exc)
            raise
        finally:
            connection.close()

    @contextmanager
    def _reading(self) -> Generator[DbConnection]:
        """A read connection with the same ``sqlite3`` error translation as the write
        path (X1), always closed. A read against a locked / corrupt / unavailable
        store is translated at this boundary rather than leaking a raw ``sqlite3.*``
        type — this is what restores the corrupt-DB self-heal (S4), the CLI exit-4
        ladder, and the daemon's structured 503 for a failed read."""
        connection = self._connect()
        try:
            yield connection
        except BaseException as exc:
            _raise_translated(exc)
            raise
        finally:
            connection.close()

    # -- reads ------------------------------------------------------------

    def find_current(self, execution_key: str) -> MlExecution | None:
        with self._reading() as connection:
            row = connection.execute(
                f"SELECT {_EXECUTION_COLUMNS} FROM executions WHERE execution_key = ? "
                "AND state = ? AND output_persisted = 1 AND superseded_at IS NULL "
                "ORDER BY id DESC LIMIT 1",
                (execution_key, ExecutionState.SUCCESS.value),
            ).fetchone()
            return self._load_execution(connection, row) if row is not None else None

    def find_all(self, execution_key: str) -> list[MlExecution]:
        with self._reading() as connection:
            rows = connection.execute(
                f"SELECT {_EXECUTION_COLUMNS} FROM executions WHERE execution_key = ? ORDER BY id",
                (execution_key,),
            ).fetchall()
            return [self._load_execution(connection, row) for row in rows]

    # -- reporting (concrete; beyond the use-case port) -------------------

    def current_execution_summaries(self) -> list[ExecutionSummary]:
        """A uniform reporting view of the current (servable) executions: key,
        kind, and the denormalized client/model — across all identity kinds."""
        with self._reading() as connection:
            rows = connection.execute(
                "SELECT e.execution_key, e.kind, i.client, i.model FROM executions e "
                "JOIN call_identities i ON i.execution_key = e.execution_key "
                "WHERE e.state = ? AND e.output_persisted = 1 AND e.superseded_at IS NULL "
                "ORDER BY e.id",
                (ExecutionState.SUCCESS.value,),
            ).fetchall()
            return [
                ExecutionSummary(execution_key=key, kind=kind, client=client, model=model)
                for (key, kind, client, model) in rows
            ]

    def find_current_by_key_prefix(self, key_prefix: str) -> list[MlExecution]:
        """The current executions whose key starts with ``key_prefix`` (so a short
        key from ``list`` is enough to ``inspect``)."""
        with self._reading() as connection:
            rows = connection.execute(
                f"SELECT {_EXECUTION_COLUMNS} FROM executions WHERE execution_key LIKE ? "
                "AND state = ? AND output_persisted = 1 AND superseded_at IS NULL ORDER BY id",
                (key_prefix + "%", ExecutionState.SUCCESS.value),
            ).fetchall()
            return [self._load_execution(connection, row) for row in rows]

    # -- write ------------------------------------------------------------

    def save(self, execution: MlExecution) -> None:
        execution_key = execution.call_identity.generate_key()
        stamped_at = self._clock.now()
        with self._write_transaction() as connection:
            self._upsert_identity(connection, execution_key, execution.call_identity)
            if self._is_servable(execution):
                self._supersede_prior_current(connection, execution_key, stamped_at)
            execution_id = self._insert_execution(connection, execution_key, execution, stamped_at)
            self._insert_artifacts(connection, execution_id, execution.artifacts)
            self._insert_token_usage(connection, execution_id, execution.token_usage)

    def record_outcome(self, execution: MlExecution) -> None:
        failure = execution.failure
        with self._write_transaction() as connection:
            row_id = self._require_row_id(connection, execution.execution_id)
            connection.execute(
                "UPDATE executions SET state = ?, failure_reason = ?, failure_message = ?, "
                "failure_exit_code = ? WHERE id = ?",
                (
                    execution.execution_state.value,
                    failure.reason.value if failure else None,
                    failure.message if failure else None,
                    failure.exit_code if failure else None,
                    row_id,
                ),
            )
            self._insert_token_usage(connection, row_id, execution.token_usage)

    def persist_artifact(self, execution_id: ExecutionId, artifact: Artifact) -> None:
        with self._write_transaction() as connection:
            row_id = self._require_row_id(connection, execution_id)
            self._insert_artifacts(connection, row_id, [artifact])

    def mark_artifacts_stored(self, execution_id: ExecutionId, blob_key: BlobKey) -> None:
        with self._write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE artifacts SET status = ?, persisted_at = ?, status_detail = NULL "
                "WHERE blob_key = ? AND execution_id = "
                "(SELECT id FROM executions WHERE execution_id = ?)",
                (
                    ArtifactStatus.STORED.value,
                    self._clock.now().isoformat(),
                    blob_key,
                    execution_id,
                ),
            )
            _require_artifact_update(cursor.rowcount, execution_id, blob_key)

    def mark_artifacts_failed(
        self, execution_id: ExecutionId, blob_key: BlobKey, detail: str
    ) -> None:
        with self._write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE artifacts SET status = ?, status_detail = ? "
                "WHERE blob_key = ? AND execution_id = "
                "(SELECT id FROM executions WHERE execution_id = ?)",
                (ArtifactStatus.FAILED.value, detail, blob_key, execution_id),
            )
            _require_artifact_update(cursor.rowcount, execution_id, blob_key)

    def runs_awaiting_persistence(self) -> list[UnpersistedRun]:
        with self._reading() as connection:
            rows = connection.execute(
                "SELECT e.execution_key, e.execution_id, a.blob_key FROM executions e "
                "JOIN artifacts a ON a.execution_id = e.id "
                "WHERE e.output_persisted = 0 AND a.status != ? AND e.execution_id IS NOT NULL "
                "AND e.id = (SELECT id FROM executions e2 WHERE e2.execution_key = e.execution_key "
                "ORDER BY e2.id DESC LIMIT 1) "
                "ORDER BY e.execution_key, a.id",
                (ArtifactStatus.STORED.value,),
            ).fetchall()
        grouped: dict[str, tuple[str, list[BlobKey]]] = {}
        for execution_key, execution_id, blob_key in rows:
            _stored_id, blob_keys = grouped.setdefault(execution_key, (execution_id, []))
            if BlobKey(blob_key) not in blob_keys:
                blob_keys.append(BlobKey(blob_key))
        return [
            UnpersistedRun(key, ExecutionId(execution_id), tuple(blob_keys))
            for key, (execution_id, blob_keys) in grouped.items()
        ]

    def finalize_output_persisted(self, execution_id: ExecutionId) -> None:
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT id, execution_key, state FROM executions WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
            if row is None:
                raise StoreConsistencyError(
                    f"finalize: no execution row for execution_id {execution_id}"
                )
            row_id, execution_key, state = row
            not_stored = connection.execute(
                "SELECT COUNT(*) FROM artifacts WHERE execution_id = ? AND status != ?",
                (row_id, ArtifactStatus.STORED.value),
            ).fetchone()[0]
            if not_stored:
                raise StoreConsistencyError(
                    f"finalize: execution {execution_id} still has {not_stored} "
                    "artifact(s) not STORED"
                )
            # A servable SUCCESS supersedes the prior current — but a recorded
            # FAILURE (record_on_error) is persisted without displacing the good
            # answer. Supersede FIRST (this row is still output_persisted=0, so the
            # supersede query cannot match it), then promote THIS exact row by id.
            if state == ExecutionState.SUCCESS.value:
                self._supersede_prior_current(connection, execution_key, self._clock.now())
            connection.execute(
                "UPDATE executions SET output_persisted = 1 WHERE id = ?",
                (row_id,),
            )

    def remove_execution(self, execution_id: ExecutionId) -> None:
        with self._write_transaction() as connection:
            row = connection.execute(
                "SELECT id, execution_key FROM executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if row is None:
                return  # already gone — idempotent cleanup
            row_id, execution_key = int(row[0]), row[1]
            connection.execute("DELETE FROM artifacts WHERE execution_id = ?", (row_id,))
            connection.execute("DELETE FROM token_usage WHERE execution_id = ?", (row_id,))
            connection.execute("DELETE FROM execution_tags WHERE execution_id = ?", (row_id,))
            connection.execute("DELETE FROM executions WHERE id = ?", (row_id,))
            # If this was the last execution for the key, drop the now-orphan identity
            # so the key leaves no trace (the interrupted run was never recorded).
            remaining = connection.execute(
                "SELECT COUNT(*) FROM executions WHERE execution_key = ?", (execution_key,)
            ).fetchone()[0]
            if not remaining:
                connection.execute(
                    "DELETE FROM call_identities WHERE execution_key = ?", (execution_key,)
                )

    @staticmethod
    def _require_row_id(connection: DbConnection, execution_id: ExecutionId) -> int:
        row = connection.execute(
            "SELECT id FROM executions WHERE execution_id = ?", (execution_id,)
        ).fetchone()
        if row is None:
            raise StoreConsistencyError(f"no execution row for execution_id {execution_id}")
        return int(row[0])

    @staticmethod
    def _upsert_identity(
        connection: DbConnection, execution_key: str, identity: CallIdentity
    ) -> None:
        serialized = serialize_identity(identity)
        connection.execute(
            "INSERT INTO call_identities "
            "(execution_key, kind, client, model, effort, identity_json) "
            "SELECT ?, ?, ?, ?, ?, ? "
            "WHERE NOT EXISTS (SELECT 1 FROM call_identities WHERE execution_key = ?)",
            (
                execution_key,
                serialized.kind,
                serialized.client,
                serialized.model,
                serialized.effort,
                serialized.identity_json,
                execution_key,
            ),
        )

    @staticmethod
    def _supersede_prior_current(
        connection: DbConnection, execution_key: str, stamped_at: datetime
    ) -> None:
        connection.execute(
            "UPDATE executions SET superseded_at = ? WHERE execution_key = ? "
            "AND state = ? AND output_persisted = 1 AND superseded_at IS NULL",
            (stamped_at.isoformat(), execution_key, ExecutionState.SUCCESS.value),
        )

    @staticmethod
    def _insert_execution(
        connection: DbConnection,
        execution_key: str,
        execution: MlExecution,
        stamped_at: datetime,
    ) -> int:
        failure = execution.failure
        cursor = connection.execute(
            "INSERT INTO executions (execution_key, kind, state, output_persisted, superseded_at, "
            "failure_reason, failure_message, failure_exit_code, created_at, execution_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                execution_key,
                execution.execution_kind.value,
                execution.execution_state.value,
                1 if execution.output_persisted else 0,
                execution.superseded_at.isoformat() if execution.superseded_at else None,
                failure.reason.value if failure else None,
                failure.message if failure else None,
                failure.exit_code if failure else None,
                stamped_at.isoformat(),
                execution.execution_id,
            ),
        )
        return int(cursor.lastrowid or 0)

    @staticmethod
    def _insert_artifacts(
        connection: DbConnection, execution_id: int, artifacts: list[Artifact]
    ) -> None:
        for artifact in artifacts:
            connection.execute(
                "INSERT INTO artifacts (execution_id, artifact_type, name, encoding, blob_key, "
                "size_bytes, status, persisted_at, status_detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    execution_id,
                    artifact.artifact_type.value,
                    artifact.name,
                    artifact.encoding,
                    artifact.blob_key,
                    artifact.size_bytes,
                    artifact.status.value,
                    artifact.persisted_at,
                    artifact.status_detail,
                ),
            )

    @staticmethod
    def _insert_token_usage(
        connection: DbConnection, execution_id: int, token_usage: TokenUsage | None
    ) -> None:
        if token_usage is None:
            return
        connection.execute(
            "INSERT INTO token_usage (execution_id, input_tokens, output_tokens, cache_read_tokens, "
            "cache_write_tokens, reasoning_tokens, cost_usd, raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                execution_id,
                token_usage.input_tokens,
                token_usage.output_tokens,
                token_usage.cache_read_tokens,
                token_usage.cache_write_tokens,
                token_usage.reasoning_tokens,
                token_usage.cost_usd,
                json.dumps(thaw(token_usage.raw)),
            ),
        )

    # -- tags (a separate annotation; never rewrites an execution) --------

    @staticmethod
    def _current_execution_id(connection: DbConnection, execution_key: str) -> int | None:
        row = connection.execute(
            "SELECT id FROM executions WHERE execution_key = ? AND state = ? "
            "AND output_persisted = 1 AND superseded_at IS NULL ORDER BY id DESC LIMIT 1",
            (execution_key, ExecutionState.SUCCESS.value),
        ).fetchone()
        return int(row[0]) if row is not None else None

    def add_tags(self, execution_key: str, tags: list[str]) -> None:
        if not tags:
            return
        with self._write_transaction() as connection:
            execution_id = self._current_execution_id(connection, execution_key)
            if execution_id is None:
                return
            for tag in tags:
                # Idempotent via UNIQUE(execution_id, tag): re-tagging never duplicates.
                connection.execute(
                    "INSERT OR IGNORE INTO execution_tags (execution_id, tag) VALUES (?, ?)",
                    (execution_id, tag),
                )

    def tags_for(self, execution_key: str) -> list[str]:
        with self._reading() as connection:
            execution_id = self._current_execution_id(connection, execution_key)
            if execution_id is None:
                return []
            rows = connection.execute(
                "SELECT tag FROM execution_tags WHERE execution_id = ? ORDER BY tag",
                (execution_id,),
            ).fetchall()
            return [tag for (tag,) in rows]

    def add_input_artifacts(self, execution_key: str, artifacts: list[Artifact]) -> None:
        if not artifacts:
            return
        with self._write_transaction() as connection:
            execution_id = self._current_execution_id(connection, execution_key)
            if execution_id is None:
                return
            # Idempotent: skip if this execution already carries input artifacts.
            placeholders = ",".join("?" * len(_INPUT_TYPE_VALUES))
            already = connection.execute(
                f"SELECT 1 FROM artifacts WHERE execution_id = ? "
                f"AND artifact_type IN ({placeholders}) LIMIT 1",
                (execution_id, *_INPUT_TYPE_VALUES),
            ).fetchone()
            if already is not None:
                return
            self._insert_artifacts(connection, execution_id, artifacts)

    # -- reconstruction ---------------------------------------------------

    def _load_execution(self, connection: DbConnection, row: _ExecutionRow) -> MlExecution:
        (
            row_id,
            execution_key,
            kind,
            state,
            output_persisted,
            superseded_at,
            failure_reason,
            failure_message,
            failure_exit_code,
            execution_id,
        ) = row
        try:
            artifacts = self._load_artifacts(connection, row_id)
            return MlExecution(
                call_identity=self._load_identity(connection, execution_key),
                execution_state=ExecutionState(state),
                execution_kind=ExecutionKind(kind),
                output_persisted=bool(output_persisted),
                # A legacy pre-0004 row has no stored id; mint one (it is historical and
                # never re-targeted, so a fresh surrogate is harmless).
                execution_id=ExecutionId(execution_id) if execution_id else ExecutionId.generate(),
                # Derived, not a column: input is persisted iff INPUT_* artifacts exist.
                input_persisted=any(a.artifact_type in INPUT_ARTIFACT_TYPES for a in artifacts),
                artifacts=artifacts,
                token_usage=self._load_token_usage(connection, row_id),
                failure=(
                    ExecutionFailure(
                        reason=FailureReason(failure_reason),
                        message=failure_message,
                        exit_code=failure_exit_code,
                    )
                    if failure_reason is not None
                    else None
                ),
                superseded_at=datetime.fromisoformat(superseded_at) if superseded_at else None,
            )
        except (ValueError, TypeError, KeyError) as exc:
            # A malformed persisted row anywhere in the reconstruction — a bad
            # kind/state/failure enum, a missing/duplicate or malformed identity, bad
            # token-usage JSON, a bad timestamp — is a corrupt cassette. Surface a
            # catchable StoreCorrupt the serve path self-heals (quarantine + re-run),
            # never a raw ValueError/TypeError that denies the whole key uncaught (X2 —
            # extends W17/S4 from the artifacts to the WHOLE row). ``_load_artifacts``
            # already raises StoreCorrupt with a per-artifact message; that passes
            # through here unchanged (it is not one of the caught types).
            raise StoreCorrupt(f"corrupt execution row for key {execution_key!r}: {exc}") from exc

    @staticmethod
    def _load_identity(connection: DbConnection, execution_key: str) -> CallIdentity:
        kind, client, model, effort, identity_json = connection.execute(
            "SELECT kind, client, model, effort, identity_json FROM call_identities "
            "WHERE execution_key = ?",
            (execution_key,),
        ).fetchone()
        return deserialize_identity(
            SerializedIdentity(
                kind=kind, client=client, model=model, effort=effort, identity_json=identity_json
            )
        )

    @staticmethod
    def _load_artifacts(connection: DbConnection, execution_id: int) -> list[Artifact]:
        rows = connection.execute(
            "SELECT artifact_type, name, encoding, blob_key, size_bytes, status, persisted_at, "
            "status_detail FROM artifacts WHERE execution_id = ? ORDER BY id",
            (execution_id,),
        ).fetchall()
        try:
            return [
                Artifact(
                    artifact_type=ArtifactType(artifact_type),
                    # Parse-at-edge (C-5): a key read from a possibly-corrupted DB row
                    # is validated here — a traversal-unsafe key is rejected before it
                    # can reach the (dumb) blob store.
                    blob_key=BlobKey(blob_key),
                    size_bytes=size_bytes,
                    name=name,
                    encoding=encoding,
                    content=None,
                    status=ArtifactStatus(status),
                    persisted_at=persisted_at,
                    status_detail=status_detail,
                )
                for (
                    artifact_type,
                    name,
                    encoding,
                    blob_key,
                    size_bytes,
                    status,
                    persisted_at,
                    status_detail,
                ) in rows
            ]
        except ValueError as exc:
            # A malformed stored row (a bad blob key or an unknown enum value) is a
            # corrupt cassette. Surface a catchable CacheError the serve path can
            # self-heal, never a raw ValueError that would deny the whole key and
            # bypass the driver error ladders (W17/S4).
            raise StoreCorrupt(f"corrupt artifact row for execution {execution_id}: {exc}") from exc

    @staticmethod
    def _load_token_usage(connection: DbConnection, execution_id: int) -> TokenUsage | None:
        row = connection.execute(
            "SELECT input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
            "reasoning_tokens, cost_usd, raw_json FROM token_usage WHERE execution_id = ?",
            (execution_id,),
        ).fetchone()
        if row is None:
            return None
        (
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_write_tokens,
            reasoning_tokens,
            cost_usd,
            raw_json,
        ) = row
        return TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            cost_usd=cost_usd,
            raw=json.loads(raw_json),
        )

    # -- retention and purge --------------------------------------------------

    def blob_keys_for_execution(self, execution_key: str) -> list[BlobKey]:
        with self._reading() as connection:
            rows = connection.execute(
                "SELECT DISTINCT a.blob_key FROM artifacts a "
                "JOIN executions e ON e.id = a.execution_id "
                "WHERE e.execution_key = ?",
                (execution_key,),
            ).fetchall()
            return [BlobKey(key) for (key,) in rows]

    def soft_purge_execution(self, execution_key: str) -> None:
        with self._write_transaction() as connection:
            connection.execute(
                "DELETE FROM artifacts WHERE execution_id IN "
                "(SELECT id FROM executions WHERE execution_key = ?)",
                (execution_key,),
            )
            connection.execute(
                "UPDATE executions SET output_persisted = 0 WHERE execution_key = ?",
                (execution_key,),
            )

    def hard_delete_execution(self, execution_key: str) -> None:
        with self._write_transaction() as connection:
            connection.execute(
                "DELETE FROM artifacts WHERE execution_id IN "
                "(SELECT id FROM executions WHERE execution_key = ?)",
                (execution_key,),
            )
            connection.execute(
                "DELETE FROM execution_tags WHERE execution_id IN "
                "(SELECT id FROM executions WHERE execution_key = ?)",
                (execution_key,),
            )
            connection.execute(
                "DELETE FROM token_usage WHERE execution_id IN "
                "(SELECT id FROM executions WHERE execution_key = ?)",
                (execution_key,),
            )
            connection.execute(
                "DELETE FROM executions WHERE execution_key = ?",
                (execution_key,),
            )
            connection.execute(
                "DELETE FROM call_identities WHERE execution_key = ?",
                (execution_key,),
            )

    def total_stored_bytes(self) -> int:
        with self._reading() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(a.size_bytes), 0) FROM artifacts a "
                "JOIN executions e ON e.id = a.execution_id "
                "WHERE e.state = ? AND e.output_persisted = 1 AND e.superseded_at IS NULL",
                (ExecutionState.SUCCESS.value,),
            ).fetchone()
            return int(row[0])

    def current_executions_with_sizes(self) -> list[ExecutionSizeEntry]:
        with self._reading() as connection:
            rows = connection.execute(
                "SELECT e.execution_key, COALESCE(SUM(a.size_bytes), 0), e.created_at "
                "FROM executions e LEFT JOIN artifacts a ON a.execution_id = e.id "
                "WHERE e.state = ? AND e.output_persisted = 1 AND e.superseded_at IS NULL "
                "GROUP BY e.execution_key, e.created_at ORDER BY e.id",
                (ExecutionState.SUCCESS.value,),
            ).fetchall()
            return [
                ExecutionSizeEntry(
                    execution_key=key,
                    total_size_bytes=int(size),
                    created_at=created_at,
                )
                for (key, size, created_at) in rows
            ]

    def executions_by_tag(self, tag: str) -> list[str]:
        with self._reading() as connection:
            rows = connection.execute(
                "SELECT DISTINCT e.execution_key FROM executions e "
                "JOIN execution_tags et ON et.execution_id = e.id "
                "WHERE et.tag = ? "
                "AND e.state = ? AND e.output_persisted = 1 AND e.superseded_at IS NULL",
                (tag, ExecutionState.SUCCESS.value),
            ).fetchall()
            return [key for (key,) in rows]

    def all_execution_keys(self) -> list[str]:
        with self._reading() as connection:
            rows = connection.execute(
                "SELECT execution_key FROM call_identities ORDER BY execution_key"
            ).fetchall()
            return [key for (key,) in rows]

    @staticmethod
    def _is_servable(execution: MlExecution) -> bool:
        return (
            execution.execution_state is ExecutionState.SUCCESS
            and execution.output_persisted
            and execution.superseded_at is None
        )


_EXECUTION_COLUMNS = (
    "id, execution_key, kind, state, output_persisted, superseded_at, "
    "failure_reason, failure_message, failure_exit_code, execution_id"
)
