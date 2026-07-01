# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionRepository: the durable, append-only execution store."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    INPUT_ARTIFACT_TYPES,
    Artifact,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
    ExecutionSizeEntry,
    ExecutionSummary,
)
from generic_ml_cache_core.common.immutable import thaw

from generic_ml_cache_adapters.adapter.out.persistence.call_identity_serialization import (
    SerializedIdentity,
    deserialize_identity,
    serialize_identity,
)
from generic_ml_cache_adapters.db import DbConnection

#: stored string values of the input artifact types, for the idempotency check.
_INPUT_TYPE_VALUES = tuple(t.value for t in INPUT_ARTIFACT_TYPES)


class ExecutionRepository(ExecutionRepositoryPort):
    """A durable, append-only execution store over any DBAPI2-compliant connection.

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

    # -- reads ------------------------------------------------------------

    def find_current(self, execution_key: str) -> MlExecution | None:
        connection = self._connect()
        try:
            row = connection.execute(
                f"SELECT {_EXECUTION_COLUMNS} FROM executions WHERE execution_key = ? "
                "AND state = ? AND output_persisted = 1 AND superseded_at IS NULL "
                "ORDER BY id DESC LIMIT 1",
                (execution_key, ExecutionState.SUCCESS.value),
            ).fetchone()
            return self._load_execution(connection, row) if row is not None else None
        finally:
            connection.close()

    def find_all(self, execution_key: str) -> list[MlExecution]:
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT {_EXECUTION_COLUMNS} FROM executions WHERE execution_key = ? ORDER BY id",
                (execution_key,),
            ).fetchall()
            return [self._load_execution(connection, row) for row in rows]
        finally:
            connection.close()

    # -- reporting (concrete; beyond the use-case port) -------------------

    def current_execution_summaries(self) -> list[ExecutionSummary]:
        """A uniform reporting view of the current (servable) executions: key,
        kind, and the denormalized client/model — across all identity kinds."""
        connection = self._connect()
        try:
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
        finally:
            connection.close()

    def find_current_by_key_prefix(self, key_prefix: str) -> list[MlExecution]:
        """The current executions whose key starts with ``key_prefix`` (so a short
        key from ``list`` is enough to ``inspect``)."""
        connection = self._connect()
        try:
            rows = connection.execute(
                f"SELECT {_EXECUTION_COLUMNS} FROM executions WHERE execution_key LIKE ? "
                "AND state = ? AND output_persisted = 1 AND superseded_at IS NULL ORDER BY id",
                (key_prefix + "%", ExecutionState.SUCCESS.value),
            ).fetchall()
            return [self._load_execution(connection, row) for row in rows]
        finally:
            connection.close()

    # -- write ------------------------------------------------------------

    def save(self, execution: MlExecution) -> None:
        execution_key = execution.call_identity.generate_key()
        stamped_at = self._clock.now()
        connection = self._connect()
        try:
            self._upsert_identity(connection, execution_key, execution.call_identity)
            if self._is_servable(execution):
                self._supersede_prior_current(connection, execution_key, stamped_at)
            execution_id = self._insert_execution(connection, execution_key, execution, stamped_at)
            self._insert_artifacts(connection, execution_id, execution.artifacts)
            self._insert_token_usage(connection, execution_id, execution.token_usage)
            connection.commit()
        finally:
            connection.close()

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
            "failure_reason, failure_message, failure_exit_code, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                "size_bytes) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    execution_id,
                    artifact.artifact_type.value,
                    artifact.name,
                    artifact.encoding,
                    artifact.blob_key,
                    artifact.size_bytes,
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
        connection = self._connect()
        try:
            execution_id = self._current_execution_id(connection, execution_key)
            if execution_id is None:
                return
            for tag in tags:
                connection.execute(
                    "INSERT INTO execution_tags (execution_id, tag) "
                    "SELECT ?, ? WHERE NOT EXISTS "
                    "(SELECT 1 FROM execution_tags WHERE execution_id = ? AND tag = ?)",
                    (execution_id, tag, execution_id, tag),
                )
            connection.commit()
        finally:
            connection.close()

    def tags_for(self, execution_key: str) -> list[str]:
        connection = self._connect()
        try:
            execution_id = self._current_execution_id(connection, execution_key)
            if execution_id is None:
                return []
            rows = connection.execute(
                "SELECT tag FROM execution_tags WHERE execution_id = ? ORDER BY tag",
                (execution_id,),
            ).fetchall()
            return [tag for (tag,) in rows]
        finally:
            connection.close()

    def add_input_artifacts(self, execution_key: str, artifacts: list[Artifact]) -> None:
        if not artifacts:
            return
        connection = self._connect()
        try:
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
            connection.commit()
        finally:
            connection.close()

    # -- reconstruction ---------------------------------------------------

    def _load_execution(self, connection: DbConnection, row: tuple) -> MlExecution:
        (
            execution_id,
            execution_key,
            kind,
            state,
            output_persisted,
            superseded_at,
            failure_reason,
            failure_message,
            failure_exit_code,
        ) = row
        artifacts = self._load_artifacts(connection, execution_id)
        return MlExecution(
            call_identity=self._load_identity(connection, execution_key),
            execution_state=ExecutionState(state),
            execution_kind=ExecutionKind(kind),
            output_persisted=bool(output_persisted),
            # Derived, not a column: input is persisted iff INPUT_* artifacts exist.
            input_persisted=any(a.artifact_type in INPUT_ARTIFACT_TYPES for a in artifacts),
            artifacts=artifacts,
            token_usage=self._load_token_usage(connection, execution_id),
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
            "SELECT artifact_type, name, encoding, blob_key, size_bytes FROM artifacts "
            "WHERE execution_id = ? ORDER BY id",
            (execution_id,),
        ).fetchall()
        return [
            Artifact(
                artifact_type=ArtifactType(artifact_type),
                blob_key=blob_key,
                size_bytes=size_bytes,
                name=name,
                encoding=encoding,
                content=None,
            )
            for (artifact_type, name, encoding, blob_key, size_bytes) in rows
        ]

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

    def blob_keys_for_execution(self, execution_key: str) -> list[str]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT DISTINCT a.blob_key FROM artifacts a "
                "JOIN executions e ON e.id = a.execution_id "
                "WHERE e.execution_key = ?",
                (execution_key,),
            ).fetchall()
            return [key for (key,) in rows]
        finally:
            connection.close()

    def blob_reference_count(self, blob_key: str) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM artifacts WHERE blob_key = ?",
                (blob_key,),
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()

    def soft_purge_execution(self, execution_key: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "DELETE FROM artifacts WHERE execution_id IN "
                "(SELECT id FROM executions WHERE execution_key = ?)",
                (execution_key,),
            )
            connection.execute(
                "UPDATE executions SET output_persisted = 0 WHERE execution_key = ?",
                (execution_key,),
            )
            connection.commit()
        finally:
            connection.close()

    def hard_delete_execution(self, execution_key: str) -> None:
        connection = self._connect()
        try:
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
            connection.commit()
        finally:
            connection.close()

    def total_stored_bytes(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT COALESCE(SUM(a.size_bytes), 0) FROM artifacts a "
                "JOIN executions e ON e.id = a.execution_id "
                "WHERE e.state = ? AND e.output_persisted = 1 AND e.superseded_at IS NULL",
                (ExecutionState.SUCCESS.value,),
            ).fetchone()
            return int(row[0])
        finally:
            connection.close()

    def current_executions_with_sizes(self) -> list[ExecutionSizeEntry]:
        connection = self._connect()
        try:
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
        finally:
            connection.close()

    def executions_by_tag(self, tag: str) -> list[str]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT DISTINCT e.execution_key FROM executions e "
                "JOIN execution_tags et ON et.execution_id = e.id "
                "WHERE et.tag = ? "
                "AND e.state = ? AND e.output_persisted = 1 AND e.superseded_at IS NULL",
                (tag, ExecutionState.SUCCESS.value),
            ).fetchall()
            return [key for (key,) in rows]
        finally:
            connection.close()

    def all_execution_keys(self) -> list[str]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT execution_key FROM call_identities ORDER BY execution_key"
            ).fetchall()
            return [key for (key,) in rows]
        finally:
            connection.close()

    @staticmethod
    def _is_servable(execution: MlExecution) -> bool:
        return (
            execution.execution_state is ExecutionState.SUCCESS
            and execution.output_persisted
            and execution.superseded_at is None
        )


_EXECUTION_COLUMNS = (
    "id, execution_key, kind, state, output_persisted, superseded_at, "
    "failure_reason, failure_message, failure_exit_code"
)
