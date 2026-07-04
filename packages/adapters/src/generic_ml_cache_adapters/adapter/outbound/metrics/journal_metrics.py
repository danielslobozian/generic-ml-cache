# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""JournalMetrics: the MetricsPort over the SQLite access registry."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.port.outbound.metrics_port import (
    MetricsPort,
    SessionEventRow,
)

from generic_ml_cache_adapters.adapter.outbound.metrics.access_registry import AccessRegistry


class JournalMetrics(MetricsPort):
    """Implements the journal over the existing best-effort access registry.

    Non-load-bearing by construction: the registry swallows its own errors, so
    ``record_event`` never raises and the projections return empty on failure —
    observability never breaks an execution. This adapter only maps the port's
    ``execution_key`` onto the registry's ``match_key``.
    """

    def __init__(self, registry: AccessRegistry) -> None:
        self._registry = registry

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
        self._registry.record(
            event,
            match_key=execution_key,
            client=client,
            model=model,
            effort=effort,
            session_id=session_id,
        )

    def hit_counts_by_key(self) -> dict[str, int]:
        return self._registry.hit_counts_by_key()

    def event_counts(self) -> dict[str, int]:
        return self._registry.event_counts()

    def session_event_counts(self, session_id: str) -> dict[str, int]:
        return self._registry.session_event_counts(session_id)

    def session_events(self, session_id: str) -> list[SessionEventRow]:
        return [
            SessionEventRow(ts=ts, event=event, client=client, model=model, execution_key=key)
            for (ts, event, client, model, key) in self._registry.session_events(session_id)
        ]

    def last_access(self) -> dict[str, float]:
        return self._registry.last_access()

    def execution_keys_for_session(self, session_id: str) -> list[str]:
        return self._registry.execution_keys_for_session(session_id)

    def delete_events_for_key(self, execution_key: str) -> None:
        self._registry.delete_events_for_key(execution_key)

    def add_session_tag(self, session_id: str, tag: str) -> None:
        self._registry.add_session_tag(session_id, tag)

    def remove_session_tag(self, session_id: str, tag: str) -> None:
        self._registry.remove_session_tag(session_id, tag)

    def session_tags(self, session_id: str) -> list[str]:
        return self._registry.session_tags_for_id(session_id)

    def session_ids_for_tag(self, tag: str) -> list[str]:
        return self._registry.session_ids_for_tag(tag)

    def set_session_spec(self, session_id: str, spec: SessionSpec) -> None:
        self._registry.set_session_spec(session_id, spec)

    def clear_session_spec(self, session_id: str) -> None:
        self._registry.clear_session_spec(session_id)

    def session_spec(self, session_id: str) -> SessionSpec | None:
        return self._registry.session_spec_for_id(session_id)

    def list_session_ids(self) -> list[str]:
        return self._registry.list_session_ids()
