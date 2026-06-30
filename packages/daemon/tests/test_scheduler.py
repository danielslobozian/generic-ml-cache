# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the eviction scheduler and its /info surface."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock

from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from starlette.testclient import TestClient

from generic_ml_cache_daemon.scheduler import EvictionScheduler, EvictionStats

# ---------------------------------------------------------------------------
# EvictionStats defaults
# ---------------------------------------------------------------------------


def test_eviction_stats_defaults():
    stats = EvictionStats()
    assert stats.last_run_at is None
    assert stats.last_executions_removed == 0
    assert stats.last_bytes_freed == 0
    assert stats.max_size is None
    assert stats.max_age is None
    assert stats.interval == 3600.0


# ---------------------------------------------------------------------------
# EvictionScheduler._run_sweep
# ---------------------------------------------------------------------------


def _fake_purge(*, quota_report=None, stale_report=None):
    purge = MagicMock()
    purge.evict_to_quota.return_value = quota_report or PurgeReport(
        executions_removed=0, bytes_freed=0, blobs_removed=0
    )
    purge.evict_stale.return_value = stale_report or PurgeReport(
        executions_removed=0, bytes_freed=0, blobs_removed=0
    )
    return purge


def test_run_sweep_calls_evict_to_quota_when_max_size_set():
    stats = EvictionStats(max_size=1024)
    purge = _fake_purge(
        quota_report=PurgeReport(executions_removed=2, bytes_freed=500, blobs_removed=2)
    )
    sched = EvictionScheduler(purge, stats)

    sched._run_sweep()

    purge.evict_to_quota.assert_called_once_with(1024)
    assert stats.last_executions_removed == 2
    assert stats.last_bytes_freed == 500


def test_run_sweep_calls_evict_stale_when_max_age_set():
    stats = EvictionStats(max_age=3600.0)
    purge = _fake_purge(
        stale_report=PurgeReport(executions_removed=1, bytes_freed=100, blobs_removed=1)
    )
    sched = EvictionScheduler(purge, stats)

    sched._run_sweep()

    purge.evict_stale.assert_called_once_with(3600.0)
    assert stats.last_executions_removed == 1
    assert stats.last_bytes_freed == 100


def test_run_sweep_merges_both_reports():
    stats = EvictionStats(max_size=1024, max_age=3600.0)
    purge = _fake_purge(
        quota_report=PurgeReport(executions_removed=1, bytes_freed=200, blobs_removed=1),
        stale_report=PurgeReport(executions_removed=2, bytes_freed=300, blobs_removed=2),
    )
    sched = EvictionScheduler(purge, stats)

    sched._run_sweep()

    assert stats.last_executions_removed == 3
    assert stats.last_bytes_freed == 500


def test_run_sweep_stamps_last_run_at():
    before = time.time()
    stats = EvictionStats(max_size=1)
    sched = EvictionScheduler(_fake_purge(), stats)
    sched._run_sweep()
    assert stats.last_run_at is not None
    assert stats.last_run_at >= before


def test_run_sweep_skips_both_when_neither_set():
    stats = EvictionStats()
    purge = _fake_purge()
    sched = EvictionScheduler(purge, stats)
    sched._run_sweep()
    purge.evict_to_quota.assert_not_called()
    purge.evict_stale.assert_not_called()


# ---------------------------------------------------------------------------
# Scheduler start / stop lifecycle
# ---------------------------------------------------------------------------


def test_scheduler_start_and_stop():
    stats = EvictionStats(max_size=1024)
    purge = _fake_purge()
    sched = EvictionScheduler(purge, stats, interval=9999)

    async def _run():
        sched.start()
        assert sched._task is not None
        await sched.stop()
        assert sched._task is None

    asyncio.run(_run())


def test_scheduler_stop_without_start_is_noop():
    stats = EvictionStats()
    sched = EvictionScheduler(_fake_purge(), stats)
    asyncio.run(sched.stop())  # must not raise


# ---------------------------------------------------------------------------
# /info eviction field (integration via TestClient)
# ---------------------------------------------------------------------------


def test_info_eviction_field_present(tmp_path: Path):
    from generic_ml_cache_daemon.app import create_app

    app = create_app(tmp_path)
    with TestClient(app) as client:
        payload = client.get("/info").json()
    assert "eviction" in payload


def test_info_eviction_defaults_when_not_configured(tmp_path: Path):
    from generic_ml_cache_daemon.app import create_app

    app = create_app(tmp_path)
    with TestClient(app) as client:
        eviction = client.get("/info").json()["eviction"]
    assert eviction["max_size"] is None
    assert eviction["max_age"] is None
    assert eviction["last_run_at"] is None
    assert eviction["last_executions_removed"] == 0
    assert eviction["last_bytes_freed"] == 0


def test_info_eviction_reflects_configured_values(tmp_path: Path):
    from generic_ml_cache_daemon.app import create_app

    app = create_app(
        tmp_path, max_size=512 * 1024 * 1024, max_age=86400.0, eviction_interval=7200.0
    )
    with TestClient(app) as client:
        eviction = client.get("/info").json()["eviction"]
    assert eviction["max_size"] == 512 * 1024 * 1024
    assert eviction["max_age"] == 86400.0
    assert eviction["interval"] == 7200.0
