# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionRepositoryPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution


class ExecutionRepositoryPort(ABC):
    """Outbound port for the structured execution record — the "database".

    It stores and returns *dehydrated* executions (structure + artifact
    references, no bytes); the use case hydrates output from the blob store.
    Executions are append-only: a call identity (one key) accumulates many
    executions over time, each one a real client call.
    """

    @abstractmethod
    def find_current(self, execution_key: str) -> Optional[MlExecution]:
        """Return the current cached answer for ``execution_key`` — the success
        that is still authoritative (state SUCCESS, not superseded, output
        persisted) — or None if there is no servable execution."""

    @abstractmethod
    def find_all(self, execution_key: str) -> List[MlExecution]:
        """Return every execution recorded for ``execution_key``, in the order
        they were saved (current, stale, and failed alike). Empty if none.

        This is the append-only history: its length is the number of real client
        calls made for this identity."""

    @abstractmethod
    def save(self, execution: MlExecution) -> None:
        """Append a new execution. If it is a servable success, atomically
        supersede the prior current execution for the same key — the supersession
        happens here, where atomicity belongs, never in the caller."""
