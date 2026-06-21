# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for JournalMetrics."""

from __future__ import annotations

from generic_ml_cache.adapter.out.metrics.access_registry import AccessRegistry
from generic_ml_cache.adapter.out.metrics.journal_metrics import JournalMetrics
from generic_ml_cache.application.port.out.metrics_port import MetricsPort


def _metrics(tmp_path) -> JournalMetrics:
    return JournalMetrics(AccessRegistry(tmp_path))


def test_is_a_metrics_port(tmp_path):
    assert isinstance(_metrics(tmp_path), MetricsPort)


def test_recorded_events_are_counted(tmp_path):
    metrics = _metrics(tmp_path)
    metrics.record_event("hit", execution_key="k1", client="claude", model="sonnet", effort="")
    metrics.record_event("record", execution_key="k2", client="claude", model="sonnet", effort="")
    metrics.record_event("hit", execution_key="k3", client="claude", model="sonnet", effort="")
    counts = metrics.event_counts()
    assert counts["hit"] == 2
    assert counts["record"] == 1


def test_hit_counts_by_key(tmp_path):
    metrics = _metrics(tmp_path)
    metrics.record_event("hit", execution_key="k1", client="c", model="m", effort="")
    metrics.record_event("hit", execution_key="k1", client="c", model="m", effort="")
    assert metrics.hit_counts_by_key()["k1"] == 2


def test_record_with_none_key_does_not_raise(tmp_path):
    metrics = _metrics(tmp_path)
    metrics.record_event("miss", execution_key=None, client="c", model="m", effort="")
    assert metrics.event_counts()["miss"] == 1


def test_events_persist_across_instances(tmp_path):
    JournalMetrics(AccessRegistry(tmp_path)).record_event(
        "record", execution_key="k1", client="c", model="m", effort=""
    )
    # A fresh adapter on the same directory sees the journalled event.
    assert JournalMetrics(AccessRegistry(tmp_path)).event_counts()["record"] == 1
