# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Outbound persistence ports for the ML-run store, role-segregated (V32).

The former fat ``ExecutionRepositoryPort`` (16 methods) is split by *consuming
use-case role* into action-and-domain-named ports, the driven-side mirror of the
inbound segregation (B-1): each use case declares only the persistence operations
it needs (Hombergs — a service depends on ``LoadAccountPort`` + ``UpdateAccount
StatePort``, not a fat ``AccountRepository``). One adapter class
(``SqliteExecutionRepository``) implements them all — one impl, many role ABCs,
exactly as one ``Service`` implements many inbound ports.

Roles: Save (append a run) · Read (replay the current answer) · Annotate (enrich
the current run) · Inspect (list/report) · Purge (retention). A method may appear
in more than one role port — role interfaces are defined by client need, so they
legitimately overlap (``total_stored_bytes`` is both an Inspect stat and a Purge
quota check; ``find_current`` is both a Read replay and an Inspect lookup).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

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


class SaveMlRunPort(ABC):
    """Append a new ML run to the store (the write side of record-or-replay)."""

    @abstractmethod
    def save(self, execution: MlExecution) -> None:
        """Append a new execution. If it is a servable success, atomically
        supersede the prior current execution for the same key — the supersession
        happens here, where atomicity belongs, never in the caller."""


class ReadMlRunPort(ABC):
    """Read the current servable answer for a key (the replay side)."""

    @abstractmethod
    def find_current(self, execution_key: str) -> MlExecution | None:
        """Return the current cached answer for ``execution_key`` — the success
        that is still authoritative (state SUCCESS, not superseded, output
        persisted) — or None if there is no servable execution."""


class AnnotateMlRunPort(ABC):
    """Enrich the current run for a key without rewriting its record."""

    @abstractmethod
    def add_tags(self, execution_key: str, tags: list[str]) -> None:
        """Attach ``tags`` to the current execution for ``execution_key``,
        idempotently — already-present tags are left untouched, new ones added.
        A separate annotation layer: this never rewrites the execution record,
        and is a no-op if there is no current execution for the key."""

    @abstractmethod
    def add_input_artifacts(self, execution_key: str, artifacts: list[Artifact]) -> None:
        """Attach input ``artifacts`` to the current execution for ``execution_key``,
        back-filling the input side of the corpus when a DATASET-depth call hits an
        entry that has none yet. Idempotent — a no-op if the current execution
        already carries input, or if there is no current execution. Like tags, this
        enriches an existing entry without rewriting its output."""


class InspectMlRunsPort(ABC):
    """List and report over stored runs (the read/reporting conversation)."""

    @abstractmethod
    def find_current(self, execution_key: str) -> MlExecution | None:
        """Return the current servable execution for ``execution_key``, or None.
        (Shared with ``ReadMlRunPort`` — inspection reads the current run too.)"""

    @abstractmethod
    def find_current_by_key_prefix(self, key_prefix: str) -> list[MlExecution]:
        """Return current executions whose key starts with ``key_prefix``
        (so a short key from ``list`` is enough to ``inspect``)."""

    @abstractmethod
    def tags_for(self, execution_key: str) -> list[str]:
        """Return the tags on the current execution for ``execution_key``, sorted;
        empty if none (or no current execution)."""

    @abstractmethod
    def current_execution_summaries(self) -> list[ExecutionSummary]:
        """A uniform reporting view of the current (servable) executions: key,
        kind, and the denormalized client/model — across all identity kinds."""

    @abstractmethod
    def total_stored_bytes(self) -> int:
        """Return the sum of size_bytes across all artifacts of all current
        (servable, non-superseded) executions. Returns 0 when the store is empty."""


class PurgeMlRunsPort(ABC):
    """Retention and explicit invalidation over stored runs (purge only)."""

    @abstractmethod
    def find_all(self, execution_key: str) -> list[MlExecution]:
        """Return every execution recorded for ``execution_key``, in the order
        they were saved (current, stale, and failed alike). Empty if none.

        This is the append-only history: its length is the number of real client
        calls made for this identity."""

    @abstractmethod
    def blob_keys_for_execution(self, execution_key: str) -> list[str]:
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
        (servable) executions — the quota check before eviction. 0 when empty.
        (Shared with ``InspectMlRunsPort``.)"""

    @abstractmethod
    def current_executions_with_sizes(self) -> list[ExecutionSizeEntry]:
        """Return one entry per current (servable) execution with its total
        artifact size and creation timestamp, used by the retention service to
        build LRU eviction order."""

    @abstractmethod
    def executions_by_tag(self, tag: str) -> list[str]:
        """Return the execution keys whose current execution carries ``tag``."""

    @abstractmethod
    def all_execution_keys(self) -> list[str]:
        """Return every distinct execution key in the store, regardless of state.
        Used by hard_delete_all to ensure no key — including those with only
        failed or superseded executions — is left behind."""
