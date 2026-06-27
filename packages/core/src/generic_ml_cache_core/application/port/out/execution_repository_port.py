# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionRepositoryPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution


@dataclass(frozen=True)
class ExecutionSummary:
    """A uniform reporting row for an execution, across all identity kinds."""

    execution_key: str
    kind: str
    client: str
    model: str


@dataclass(frozen=True)
class ExecutionSizeEntry:
    """A size-reporting row used by the retention service for LRU eviction ordering."""

    execution_key: str
    total_size_bytes: int
    created_at: str  # ISO-format string; empty string when not tracked (in-memory)


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

    # -- retention and purge --------------------------------------------------

    @abstractmethod
    def blob_keys_for_execution(self, execution_key: str) -> List[str]:
        """Return the distinct blob keys referenced by ALL stored executions for
        ``execution_key`` (current and historical). Called before a soft purge so
        the caller can check reference counts before removing blobs."""

    @abstractmethod
    def blob_reference_count(self, blob_key: str) -> int:
        """Return the number of artifact rows across the entire store still
        referencing ``blob_key``. After a soft purge drops an execution's artifact
        rows, a count of zero means no other execution references the blob and the
        caller may safely remove it from the blob store."""

    @abstractmethod
    def soft_purge_execution(self, execution_key: str) -> None:
        """Remove all artifact rows for every execution under ``execution_key`` and
        mark those executions as not output-persisted (no longer replayable). The
        execution records, token_usage rows, tags, and access events are preserved —
        statistics and audit trail survive; only the stored bytes are released."""

    @abstractmethod
    def hard_delete_execution(self, execution_key: str) -> None:
        """Delete every DB row for ``execution_key``: all executions, their
        artifacts, tags, token_usage, and the call identity. Nothing survives."""

    @abstractmethod
    def total_stored_bytes(self) -> int:
        """Return the sum of size_bytes across all artifacts of all current
        (servable, non-superseded) executions. Returns 0 when the store is empty."""

    @abstractmethod
    def current_executions_with_sizes(self) -> List[ExecutionSizeEntry]:
        """Return one entry per current (servable) execution with its total
        artifact size and creation timestamp, used by the retention service to
        build LRU eviction order."""

    @abstractmethod
    def executions_by_tag(self, tag: str) -> List[str]:
        """Return the execution keys whose current execution carries ``tag``."""

    @abstractmethod
    def all_execution_keys(self) -> List[str]:
        """Return every distinct execution key in the store, regardless of state.
        Used by hard_delete_all to ensure no key — including those with only
        failed or superseded executions — is left behind."""

    # -- reporting ------------------------------------------------------------

    @abstractmethod
    def current_execution_summaries(self) -> List[ExecutionSummary]:
        """A uniform reporting view of the current (servable) executions: key,
        kind, and the denormalized client/model — across all identity kinds."""

    @abstractmethod
    def find_current_by_key_prefix(self, key_prefix: str) -> List[MlExecution]:
        """Return current executions whose key starts with ``key_prefix``
        (so a short key from ``list`` is enough to ``inspect``)."""
