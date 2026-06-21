# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""InMemoryExecutionRepository: an ephemeral, append-only execution store."""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Optional

from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)


class InMemoryExecutionRepository(ExecutionRepositoryPort):
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
        self._by_key: Dict[str, List[MlExecution]] = {}

    def find_current(self, execution_key: str) -> Optional[MlExecution]:
        for execution in self._by_key.get(execution_key, []):
            if self._is_servable(execution):
                return replace(execution)
        return None

    def find_all(self, execution_key: str) -> List[MlExecution]:
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
