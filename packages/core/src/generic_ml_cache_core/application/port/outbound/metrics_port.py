# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MetricsPort."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.session.session_event_row import SessionEventRow
from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec

__all__ = ["MetricsPort", "SessionEventRow"]


class MetricsPort(ABC):
    """Outbound port for the call journal: append events, query projections.

    Non-load-bearing by contract: record_event must never raise, because
    observability must never break an execution. Implementations swallow
    their own errors at the adapter level.

    Events are the source of truth. hit_counts_by_key, event_counts, and
    last_access are projections over the journal, not stored truths.
    """

    @abstractmethod
    def record_event(
        self,
        event: str,
        *,
        execution_key: str | None,
        client: str,
        model: str,
        effort: str,
        session_id: str | None = None,
    ) -> None:
        """Append one journal event. Must never raise. ``session_id`` groups events
        into a workflow session; it is journal metadata only, never part of the key."""

    @abstractmethod
    def hit_counts_by_key(self) -> dict[str, int]:
        """Return {execution_key: hit_count} across all HIT events.

        An empty dict is the correct response when no data is available.
        """

    @abstractmethod
    def event_counts(self) -> dict[str, int]:
        """Return {event_name: count} across all recorded events.

        An empty dict is the correct response when no data is available.
        """

    @abstractmethod
    def session_event_counts(self, session_id: str) -> dict[str, int]:
        """Return {event_name: count} for the events recorded under ``session_id``.

        An empty dict is the correct response for an unknown session or no data.
        """

    @abstractmethod
    def session_events(self, session_id: str) -> list[SessionEventRow]:
        """Return the events recorded under ``session_id``, oldest first, each with
        timestamp / event / client / model / execution_key — enough to build a session
        report (per-day activity and per-model usage). Empty for an unknown session.
        """

    @abstractmethod
    def last_access(self) -> dict[str, float]:
        """Return {execution_key: epoch_seconds} of the latest event per key.

        Used for LRU eviction ordering. An empty dict is the correct response
        when no data is available.
        """

    @abstractmethod
    def execution_keys_for_session(self, session_id: str) -> list[str]:
        """Return the distinct execution keys recorded under ``session_id``.
        Used by the purge service to resolve session-scoped purge targets.
        An empty list is the correct response for an unknown session.
        """

    @abstractmethod
    def delete_events_for_key(self, execution_key: str) -> None:
        """Remove all journal events for ``execution_key``. Called during a
        hard delete to erase the key's access history. Must never raise."""

    @abstractmethod
    def add_session_tag(self, session_id: str, tag: str) -> None:
        """Attach ``tag`` to ``session_id``. Must never raise."""

    @abstractmethod
    def remove_session_tag(self, session_id: str, tag: str) -> None:
        """Detach ``tag`` from ``session_id``. No-op when the tag is absent.
        Must never raise."""

    @abstractmethod
    def session_tags(self, session_id: str) -> list[str]:
        """Return the distinct tags attached to ``session_id``.
        Empty list for an unknown session."""

    @abstractmethod
    def session_ids_for_tag(self, tag: str) -> list[str]:
        """Return the distinct session ids carrying ``tag``.
        Empty list when no sessions have that tag."""

    @abstractmethod
    def set_session_spec(self, session_id: str, spec: SessionSpec) -> None:
        """Attach (or replace) the execution spec for ``session_id``. Must never raise."""

    @abstractmethod
    def clear_session_spec(self, session_id: str) -> None:
        """Remove the execution spec for ``session_id``. No-op if absent. Must never raise."""

    @abstractmethod
    def session_spec(self, session_id: str) -> SessionSpec | None:
        """Return the execution spec for ``session_id``, or None if unset."""

    @abstractmethod
    def list_session_ids(self) -> list[str]:
        """Return all known session IDs (empty list if none or on error)."""
