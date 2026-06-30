# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StoreStatsService — the store-stats capability (journal read aggregates)."""

from __future__ import annotations

from generic_ml_cache_core.application.port.inbound.store_stats.event_counts_use_case import (
    EventCountsUseCase,
)
from generic_ml_cache_core.application.port.inbound.store_stats.hit_counts_by_key_use_case import (
    HitCountsByKeyUseCase,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


class StoreStatsService(EventCountsUseCase, HitCountsByKeyUseCase):
    """Event and hit aggregates via the metrics out-port."""

    def __init__(self, metrics: MetricsPort) -> None:
        self._metrics = metrics

    def event_counts(self) -> dict[str, int]:
        return self._metrics.event_counts()

    def hit_counts_by_key(self) -> dict[str, int]:
        return self._metrics.hit_counts_by_key()
