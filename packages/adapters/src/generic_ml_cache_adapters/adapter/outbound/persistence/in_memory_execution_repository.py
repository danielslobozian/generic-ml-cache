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

from generic_ml_cache_adapters.adapter.outbound.persistence.call_identity_serialization import (
    serialize_identity,
)


class InMemoryExecutionRepository(
    SaveMlRunPort,
    ReadMlRunPort,
    AnnotateMlRunPort,
    InspectMlRunsPort,
    PurgeMlRunsPort,
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
        self._tags_by_key: dict[str, set[str]] = {}

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

    def mark_artifacts_stored(self, execution_key: str, blob_key: str) -> None:
        execution = self._latest(execution_key)
        if execution is None:
            return
        persisted_at = self._clock.now().isoformat()
        execution.artifacts[:] = [
            replace(a, status=ArtifactStatus.STORED, persisted_at=persisted_at, status_detail=None)
            if a.blob_key == blob_key
            else a
            for a in execution.artifacts
        ]

    def mark_artifacts_failed(self, execution_key: str, blob_key: str, detail: str) -> None:
        execution = self._latest(execution_key)
        if execution is None:
            return
        execution.artifacts[:] = [
            replace(a, status=ArtifactStatus.FAILED, status_detail=detail)
            if a.blob_key == blob_key
            else a
            for a in execution.artifacts
        ]

    def finalize_output_persisted(self, execution_key: str) -> None:
        execution = self._latest(execution_key)
        if execution is None:
            return
        # A servable SUCCESS supersedes the prior current; a recorded FAILURE
        # (record_on_error) is persisted without displacing the good answer. The new
        # row is still output_persisted=0 here, so _is_servable excludes it.
        if execution.execution_state is ExecutionState.SUCCESS:
            superseded_at = self._clock.now()
            for prior in self._by_key.get(execution_key, []):
                if self._is_servable(prior):
                    prior.superseded_at = superseded_at
        execution.output_persisted = True

    def _latest(self, execution_key: str) -> MlExecution | None:
        history = self._by_key.get(execution_key, [])
        return history[-1] if history else None

    def add_tags(self, execution_key: str, tags: list[str]) -> None:
        # Tags the key's current execution; a no-op when there is none.
        if not tags or self.find_current(execution_key) is None:
            return
        self._tags_by_key.setdefault(execution_key, set()).update(tags)

    def tags_for(self, execution_key: str) -> list[str]:
        if self.find_current(execution_key) is None:
            return []
        return sorted(self._tags_by_key.get(execution_key, set()))

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

    def blob_keys_for_execution(self, execution_key: str) -> list[str]:
        return list(
            {
                a.blob_key
                for execution in self._by_key.get(execution_key, [])
                for a in execution.artifacts
            }
        )

    def blob_reference_count(self, blob_key: str) -> int:
        # Only STORED artifacts truly reference a blob (a PENDING/FAILED row's blob
        # may not exist), so only they keep it alive for GC.
        return sum(
            1
            for executions in self._by_key.values()
            for execution in executions
            for a in execution.artifacts
            if a.blob_key == blob_key and a.status is ArtifactStatus.STORED
        )

    def soft_purge_execution(self, execution_key: str) -> None:
        for execution in self._by_key.get(execution_key, []):
            execution.artifacts.clear()
            execution.output_persisted = False
            execution.input_persisted = False

    def hard_delete_execution(self, execution_key: str) -> None:
        self._by_key.pop(execution_key, None)
        self._tags_by_key.pop(execution_key, None)

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
        return [
            key
            for key, executions in self._by_key.items()
            if any(self._is_servable(e) for e in executions)
            and tag in self._tags_by_key.get(key, set())
        ]

    def all_execution_keys(self) -> list[str]:
        return list(self._by_key.keys())

    # -- reporting ------------------------------------------------------------

    def current_execution_summaries(self) -> list[ExecutionSummary]:
        summaries: list[ExecutionSummary] = []
        for key, executions in self._by_key.items():
            for execution in executions:
                if not self._is_servable(execution):
                    continue
                serialized = serialize_identity(execution.call_identity)
                summaries.append(
                    ExecutionSummary(
                        execution_key=key,
                        kind=execution.execution_kind.value,
                        client=serialized.client,
                        model=serialized.model,
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
