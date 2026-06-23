# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""JournalMetrics: the MetricsPort over the SQLite access registry."""

from __future__ import annotations

from typing import Dict, Optional

from generic_ml_cache_core.adapter.out.metrics.access_registry import AccessRegistry
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


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

    def last_access(self) -> Dict[str, float]:
        return self._registry.last_access()
