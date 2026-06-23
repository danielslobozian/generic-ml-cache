# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for JournalMetrics."""

from __future__ import annotations

import sqlite3

from generic_ml_cache_core.adapter.out.metrics.access_registry import AccessRegistry
from generic_ml_cache_core.adapter.out.metrics.journal_metrics import JournalMetrics
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


def _metrics(tmp_path) -> JournalMetrics:
    return JournalMetrics(AccessRegistry(tmp_path))


def _session_ids(tmp_path):
    conn = sqlite3.connect(tmp_path / "registry.sqlite3")
    try:
        return [r[0] for r in conn.execute("SELECT session_id FROM access_events ORDER BY id")]
    finally:
        conn.close()


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


def test_session_id_is_recorded_on_the_event(tmp_path):
    metrics = _metrics(tmp_path)
    metrics.record_event(
        "record", execution_key="k", client="c", model="m", effort="", session_id="sess-1"
    )
    metrics.record_event("hit", execution_key="k", client="c", model="m", effort="")  # no session
    assert _session_ids(tmp_path) == ["sess-1", None]


def test_pre_sessions_registry_is_migrated_in_place(tmp_path):
    # A registry created before sessions existed: access_events without session_id.
    path = tmp_path / "registry.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE access_events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, event TEXT, "
        "match_key TEXT, client TEXT, model TEXT, effort TEXT)"
    )
    conn.execute("INSERT INTO access_events (ts, event) VALUES ('t', 'hit')")
    conn.commit()
    conn.close()

    # Recording with a session_id triggers the additive ALTER and stores it.
    _metrics(tmp_path).record_event(
        "record", execution_key="k", client="c", model="m", effort="", session_id="s"
    )
    assert _session_ids(tmp_path) == [None, "s"]  # old row NULL, new row carries the session
