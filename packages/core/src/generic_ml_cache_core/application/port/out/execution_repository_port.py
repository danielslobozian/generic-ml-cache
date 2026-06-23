# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionRepositoryPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact
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

    @abstractmethod
    def add_tags(self, execution_key: str, tags: List[str]) -> None:
        """Attach ``tags`` to the current execution for ``execution_key``,
        idempotently — already-present tags are left untouched, new ones added.
        A separate annotation layer: this never rewrites the execution record,
        and is a no-op if there is no current execution for the key."""

    @abstractmethod
    def tags_for(self, execution_key: str) -> List[str]:
        """Return the tags on the current execution for ``execution_key``, sorted;
        empty if none (or no current execution)."""

    @abstractmethod
    def add_input_artifacts(self, execution_key: str, artifacts: List[Artifact]) -> None:
        """Attach input ``artifacts`` to the current execution for ``execution_key``,
        back-filling the input side of the corpus when a DATASET-depth call hits an
        entry that has none yet. Idempotent — a no-op if the current execution
        already carries input, or if there is no current execution. Like tags, this
        enriches an existing entry without rewriting its output."""
