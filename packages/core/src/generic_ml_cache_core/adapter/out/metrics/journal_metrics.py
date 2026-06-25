# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""JournalMetrics: the MetricsPort over the SQLite access registry."""

from __future__ import annotations

from typing import Dict, List, Optional

from generic_ml_cache_core.adapter.out.metrics.access_registry import AccessRegistry
from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort, SessionEventRow


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
        execution_key: Optional[str],
        client: str,
        model: str,
        effort: str,
        session_id: Optional[str] = None,
    ) -> None:
        self._registry.record(
            event,
            match_key=execution_key,
            client=client,
            model=model,
            effort=effort,
            session_id=session_id,
        )

    def hit_counts_by_key(self) -> Dict[str, int]:
        return self._registry.hit_counts_by_key()

    def event_counts(self) -> Dict[str, int]:
        return self._registry.event_counts()

    def session_event_counts(self, session_id: str) -> Dict[str, int]:
        return self._registry.session_event_counts(session_id)

    def session_events(self, session_id: str) -> List[SessionEventRow]:
        return [
            SessionEventRow(ts=ts, event=event, client=client, model=model, execution_key=key)
            for (ts, event, client, model, key) in self._registry.session_events(session_id)
        ]

    def last_access(self) -> Dict[str, float]:
        return self._registry.last_access()

    def execution_keys_for_session(self, session_id: str) -> List[str]:
        return self._registry.execution_keys_for_session(session_id)

    def delete_events_for_key(self, execution_key: str) -> None:
        self._registry.delete_events_for_key(execution_key)

    def add_session_tag(self, session_id: str, tag: str) -> None:
        self._registry.add_session_tag(session_id, tag)

    def remove_session_tag(self, session_id: str, tag: str) -> None:
        self._registry.remove_session_tag(session_id, tag)

    def session_tags(self, session_id: str) -> List[str]:
        return self._registry.session_tags_for_id(session_id)

    def session_ids_for_tag(self, tag: str) -> List[str]:
        return self._registry.session_ids_for_tag(tag)

    def set_session_spec(self, session_id: str, spec: SessionSpec) -> None:
        self._registry.set_session_spec(session_id, spec)

    def clear_session_spec(self, session_id: str) -> None:
        self._registry.clear_session_spec(session_id)

    def session_spec(self, session_id: str) -> Optional[SessionSpec]:
        return self._registry.session_spec_for_id(session_id)

    def list_session_ids(self) -> List[str]:
        return self._registry.list_session_ids()
