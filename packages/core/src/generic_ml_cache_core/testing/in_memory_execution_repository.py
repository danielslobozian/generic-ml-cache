# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""InMemoryExecutionRepository: an ephemeral, append-only execution store."""

from __future__ import annotations

from dataclasses import replace

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    INPUT_ARTIFACT_TYPES,
    Artifact,
    ArtifactStatus,
)
from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
from generic_ml_cache_core.application.domain.model.execution.execution_id import ExecutionId
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
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
from generic_ml_cache_core.common.errors import StoreConsistencyError


def _require_artifact_update(matched: int, execution_id: ExecutionId, blob_key: BlobKey) -> None:
    """A mark_* that matched no artifact is a stale/mistargeted write — fail loud
    rather than no-op, matching the SQLite adapter's rowcount guard (W1)."""
    if matched == 0:
        raise StoreConsistencyError(
            f"no artifact row for execution {execution_id} / blob {blob_key} to update"
        )


class InMemoryExecutionRepository(
    SaveMlRunPort,
    ReadMlRunPort,
    AnnotateMlRunPort,
    InspectMlRunsPort,
    PurgeMlRunsPort,
    RepairMlRunsPort,
):
    """An in-memory, append-only implementation of the execution repository.

    Holds only structure: every saved execution is dehydrated (artifact bytes
    dropped) before storage, so the repository never carries output content —
    the bytes live in the blob store. Suitable as an ephemeral cache for a
    library consumer and as a faithful test double that forces the use case down
    the same hydrate-from-blob path the durable adapter will.

    The clock is injected (it stamps supersession), so time is deterministic.
    """

    def __init__(self, clock: ClockPort) -> None:
        self._clock = clock
        self._by_key: dict[str, list[MlExecution]] = {}
        # Tags belong to an execution ROW (its execution_id), NOT the key (Y16) — the
        # durable SQLite store tags execution_tags.execution_id, so after a supersession
        # the new current row starts untagged and the old tags do not carry over. Keying
        # by execution_id keeps this test double faithful to that row-scoped semantics.
        self._tags_by_execution_id: dict[ExecutionId, set[str]] = {}

    def find_current(self, execution_key: str) -> MlExecution | None:
        for execution in self._by_key.get(execution_key, []):
            if self._is_servable(execution):
                return replace(execution)
        return None

    def find_all(self, execution_key: str) -> list[MlExecution]:
        return [replace(execution) for execution in self._by_key.get(execution_key, [])]

    def save(self, execution: MlExecution) -> None:
        execution_key = execution.call_identity.generate_key()
        stored = self._dehydrate(execution)
        history = self._by_key.setdefault(execution_key, [])
        if self._is_servable(stored):
            superseded_at = self._clock.now()
            for prior in history:
                if self._is_servable(prior):
                    prior.superseded_at = superseded_at
        history.append(stored)

    def record_outcome(self, execution: MlExecution) -> None:
        _key, stored = self._require_by_id(execution.execution_id)
        stored.execution_state = execution.execution_state
        stored.failure = execution.failure
        stored.token_usage = execution.token_usage

    def persist_artifact(self, execution_id: ExecutionId, artifact: Artifact) -> None:
        _key, stored = self._require_by_id(execution_id)
        stored.artifacts.append(replace(artifact, content=None))

    def mark_artifacts_stored(self, execution_id: ExecutionId, blob_key: BlobKey) -> None:
        _key, execution = self._require_by_id(execution_id)
        persisted_at = self._clock.now().isoformat()
        matched = self._resolve_artifacts(
            execution, blob_key, status=ArtifactStatus.STORED, persisted_at=persisted_at
        )
        _require_artifact_update(matched, execution_id, blob_key)

    def mark_artifacts_failed(
        self, execution_id: ExecutionId, blob_key: BlobKey, detail: str
    ) -> None:
        _key, execution = self._require_by_id(execution_id)
        matched = self._resolve_artifacts(
            execution, blob_key, status=ArtifactStatus.FAILED, status_detail=detail
        )
        _require_artifact_update(matched, execution_id, blob_key)

    def finalize_output_persisted(self, execution_id: ExecutionId) -> None:
        execution_key, execution = self._require_by_id(execution_id)
        not_stored = sum(1 for a in execution.artifacts if a.status is not ArtifactStatus.STORED)
        if not_stored:
            raise StoreConsistencyError(
                f"finalize: execution {execution_id} still has {not_stored} artifact(s) not STORED"
            )
        # A servable SUCCESS supersedes the prior current; a recorded FAILURE
        # (record_on_error) is persisted without displacing the good answer. This
        # row is still output_persisted=0 here, so _is_servable excludes it.
        if execution.execution_state is ExecutionState.SUCCESS:
            superseded_at = self._clock.now()
            for prior in self._by_key.get(execution_key, []):
                if self._is_servable(prior):
                    prior.superseded_at = superseded_at
        execution.output_persisted = True

    @staticmethod
    def _resolve_artifacts(
        execution: MlExecution,
        blob_key: BlobKey,
        *,
        status: ArtifactStatus,
        persisted_at: str | None = None,
        status_detail: str | None = None,
    ) -> int:
        """Flip every artifact referencing ``blob_key`` to ``status`` in place;
        return how many rows matched (0 means nothing to update — a stale write)."""
        matched = 0
        resolved: list[Artifact] = []
        for artifact in execution.artifacts:
            if artifact.blob_key == blob_key:
                matched += 1
                resolved.append(
                    replace(
                        artifact,
                        status=status,
                        persisted_at=persisted_at
                        if persisted_at is not None
                        else artifact.persisted_at,
                        status_detail=status_detail,
                    )
                )
            else:
                resolved.append(artifact)
        execution.artifacts[:] = resolved
        return matched

    def remove_execution(self, execution_id: ExecutionId) -> None:
        located = self._locate_by_id(execution_id)
        if located is None:
            return  # already gone — idempotent cleanup
        execution_key, execution = located
        self._by_key[execution_key].remove(execution)
        # Tags are row-scoped (by execution_id), so dropping a row drops exactly its tags.
        self._tags_by_execution_id.pop(execution.execution_id, None)
        # If it was the last execution for the key, drop the key entirely so an
        # interrupted run leaves no trace (matching the durable adapter).
        if not self._by_key[execution_key]:
            self._by_key.pop(execution_key)

    def _require_by_id(self, execution_id: ExecutionId) -> tuple[str, MlExecution]:
        located = self._locate_by_id(execution_id)
        if located is None:
            raise StoreConsistencyError(f"no execution row for execution_id {execution_id}")
        return located

    def _locate_by_id(self, execution_id: ExecutionId) -> tuple[str, MlExecution] | None:
        for key, history in self._by_key.items():
            for execution in history:
                if execution.execution_id == execution_id:
                    return key, execution
        return None

    def runs_awaiting_persistence(self) -> list[UnpersistedRun]:
        runs: list[UnpersistedRun] = []
        for key, history in self._by_key.items():
            latest = history[-1] if history else None
            if latest is None or latest.output_persisted:
                continue
            blob_keys: list[BlobKey] = []
            for a in latest.artifacts:
                if a.status is not ArtifactStatus.STORED and a.blob_key not in blob_keys:
                    blob_keys.append(a.blob_key)
            if blob_keys:
                runs.append(UnpersistedRun(key, latest.execution_id, tuple(blob_keys)))
        return runs

    def _current_execution_id(self, execution_key: str) -> ExecutionId | None:
        current = self.find_current(execution_key)
        return current.execution_id if current is not None else None

    def add_tags(self, execution_key: str, tags: list[str]) -> None:
        # Tags the key's CURRENT execution row (by execution_id); a no-op when there
        # is none. Matches SQLite's INSERT INTO execution_tags(execution_id, tag).
        if not tags:
            return
        execution_id = self._current_execution_id(execution_key)
        if execution_id is None:
            return
        self._tags_by_execution_id.setdefault(execution_id, set()).update(tags)

    def tags_for(self, execution_key: str) -> list[str]:
        execution_id = self._current_execution_id(execution_key)
        if execution_id is None:
            return []
        return sorted(self._tags_by_execution_id.get(execution_id, set()))

    def add_input_artifacts(self, execution_key: str, artifacts: list[Artifact]) -> None:
        # Back-fill the input onto the key's current execution; idempotent and a
        # no-op when there is none or it already carries input.
        if not artifacts:
            return
        for execution in self._by_key.get(execution_key, []):
            if not self._is_servable(execution):
                continue
            if any(a.artifact_type in INPUT_ARTIFACT_TYPES for a in execution.artifacts):
                return
            execution.artifacts.extend(replace(a, content=None) for a in artifacts)
            execution.input_persisted = True
            return

    # -- retention and purge --------------------------------------------------

    def blob_keys_for_execution(self, execution_key: str) -> list[BlobKey]:
        return list(
            {
                a.blob_key
                for execution in self._by_key.get(execution_key, [])
                for a in execution.artifacts
            }
        )

    def soft_purge_execution(self, execution_key: str) -> None:
        for execution in self._by_key.get(execution_key, []):
            execution.artifacts.clear()
            execution.output_persisted = False
            execution.input_persisted = False

    def hard_delete_execution(self, execution_key: str) -> None:
        # Drop every row for the key AND each row's tags (SQLite DELETEs execution_tags
        # for all the key's execution_ids). soft_purge, in contrast, keeps the tag rows
        # (it only clears artifacts + output_persisted), matching the durable adapter.
        for execution in self._by_key.pop(execution_key, []):
            self._tags_by_execution_id.pop(execution.execution_id, None)

    def total_stored_bytes(self) -> int:
        return sum(
            a.size_bytes
            for executions in self._by_key.values()
            for execution in executions
            if self._is_servable(execution)
            for a in execution.artifacts
        )

    def current_executions_with_sizes(self) -> list[ExecutionSizeEntry]:
        return [
            ExecutionSizeEntry(
                execution_key=key,
                total_size_bytes=sum(a.size_bytes for a in execution.artifacts),
                created_at="",
            )
            for key, executions in self._by_key.items()
            for execution in executions
            if self._is_servable(execution)
        ]

    def executions_by_tag(self, tag: str) -> list[str]:
        # A key matches when its CURRENT execution row carries the tag — a tag on a
        # superseded or soft-purged (non-current) row does not surface the key, matching
        # SQLite's JOIN on the current execution.
        matched: list[str] = []
        for key in self._by_key:
            execution_id = self._current_execution_id(key)
            if execution_id is not None and tag in self._tags_by_execution_id.get(
                execution_id, set()
            ):
                matched.append(key)
        return matched

    def all_execution_keys(self) -> list[str]:
        return list(self._by_key.keys())

    # -- reporting ------------------------------------------------------------

    def current_execution_summaries(self) -> list[ExecutionSummary]:
        summaries: list[ExecutionSummary] = []
        for key, executions in self._by_key.items():
            for execution in executions:
                if not self._is_servable(execution):
                    continue
                summaries.append(
                    ExecutionSummary(
                        execution_key=key,
                        kind=execution.execution_kind.value,
                        client=execution.call_identity.summary_client,
                        model=execution.call_identity.summary_model,
                    )
                )
        return summaries

    def find_current_by_key_prefix(self, key_prefix: str) -> list[MlExecution]:
        return [
            replace(execution)
            for key, executions in self._by_key.items()
            if key.startswith(key_prefix)
            for execution in executions
            if self._is_servable(execution)
        ]

    @staticmethod
    def _is_servable(execution: MlExecution) -> bool:
        """A servable execution is the current cached answer: a persisted success
        that has not been superseded."""
        return (
            execution.execution_state is ExecutionState.SUCCESS
            and execution.output_persisted
            and execution.superseded_at is None
        )

    @staticmethod
    def _dehydrate(execution: MlExecution) -> MlExecution:
        """Return a copy whose artifacts carry no bytes — the repository stores
        structure only; the bytes belong to the blob store."""
        dehydrated_artifacts = [replace(artifact, content=None) for artifact in execution.artifacts]
        return replace(execution, artifacts=dehydrated_artifacts)
