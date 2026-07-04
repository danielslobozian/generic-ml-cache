# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for StoreStatsService (the store-stats inbound capability)."""

from generic_ml_cache_core.application.usecase.store_stats_service import StoreStatsService


class _FakeMetrics:
    def event_counts(self):
        return {"record": 3, "hit": 5}

    def hit_counts_by_key(self):
        return {"k1": 2, "k2": 1}


def test_event_counts_delegates():
    assert StoreStatsService(_FakeMetrics()).event_counts() == {"record": 3, "hit": 5}  # type: ignore[arg-type]


def test_hit_counts_by_key_delegates():
    assert StoreStatsService(_FakeMetrics()).hit_counts_by_key() == {"k1": 2, "k2": 1}  # type: ignore[arg-type]
