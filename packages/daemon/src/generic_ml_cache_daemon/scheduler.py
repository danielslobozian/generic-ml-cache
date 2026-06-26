# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Background eviction scheduler.

Runs size-quota enforcement (evict_to_quota) and time-based eviction
(evict_stale) on a fixed interval while the daemon is running.  The last
run result is stored in EvictionStats so the /info endpoint can surface it.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from generic_ml_cache_core.application.usecase.purge_service import PurgeService

_DEFAULT_INTERVAL = 3600.0  # seconds between eviction sweeps


@dataclass
class EvictionStats:
    """Last-run snapshot exposed via GET /info."""

    last_run_at: Optional[float] = None  # Unix epoch, None = never run
    last_executions_removed: int = 0
    last_bytes_freed: int = 0
    max_size: Optional[int] = None  # bytes, None = disabled
    max_age: Optional[float] = None  # seconds, None = disabled
    interval: float = _DEFAULT_INTERVAL


class EvictionScheduler:
    """Runs periodic eviction in an asyncio background task.

    Create one instance per daemon lifetime, start it with ``start()``, and
    stop it with ``stop()``.  Results are accumulated in ``stats`` so callers
    can inspect the last sweep without waiting for the next one.
    """

    def __init__(
        self,
        purge: PurgeService,
        stats: EvictionStats,
        *,
        interval: float = _DEFAULT_INTERVAL,
    ) -> None:
        self._purge = purge
        self._stats = stats
        self._interval = interval
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    def start(self) -> None:
        """Schedule the recurring eviction task on the running event loop."""
        self._task = asyncio.create_task(self._loop(), name="gmlcache-eviction")

    async def stop(self) -> None:
        """Cancel the background task and wait for it to finish."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            self._run_sweep()

    def _run_sweep(self) -> None:
        """Execute one eviction sweep and update stats."""
        report = PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        if self._stats.max_size is not None:
            r = self._purge.evict_to_quota(self._stats.max_size)
            report = _merge(report, r)
        if self._stats.max_age is not None:
            r = self._purge.evict_stale(self._stats.max_age)
            report = _merge(report, r)
        self._stats.last_run_at = time.time()
        self._stats.last_executions_removed = report.executions_removed
        self._stats.last_bytes_freed = report.bytes_freed


def _merge(a: PurgeReport, b: PurgeReport) -> PurgeReport:
    return PurgeReport(
        executions_removed=a.executions_removed + b.executions_removed,
        bytes_freed=a.bytes_freed + b.bytes_freed,
        blobs_removed=a.blobs_removed + b.blobs_removed,
    )
