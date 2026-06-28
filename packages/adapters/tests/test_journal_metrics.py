# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for JournalMetrics."""

from __future__ import annotations

import sqlite3

from generic_ml_cache_adapters.migration_runner import run_migrations
from generic_ml_cache_adapters.adapter.out.metrics.access_registry import AccessRegistry
from generic_ml_cache_adapters.adapter.out.metrics.journal_metrics import JournalMetrics
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


def _make_factory(db_path):
    def _connect():
        return sqlite3.connect(str(db_path))

    return _connect


def _metrics(tmp_path) -> JournalMetrics:
    factory = _make_factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    return JournalMetrics(AccessRegistry(factory))


def _session_ids(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "gmlcache.sqlite3"))
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
    factory = _make_factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    JournalMetrics(AccessRegistry(factory)).record_event(
        "record", execution_key="k1", client="c", model="m", effort=""
    )
    # A fresh adapter on the same database sees the journalled event.
    assert JournalMetrics(AccessRegistry(factory)).event_counts()["record"] == 1


def test_session_id_is_recorded_on_the_event(tmp_path):
    metrics = _metrics(tmp_path)
    metrics.record_event(
        "record", execution_key="k", client="c", model="m", effort="", session_id="sess-1"
    )
    metrics.record_event("hit", execution_key="k", client="c", model="m", effort="")  # no session
    assert _session_ids(tmp_path) == ["sess-1", None]


def test_session_event_counts_are_scoped_to_the_session(tmp_path):
    metrics = _metrics(tmp_path)
    metrics.record_event(
        "record", execution_key="k1", client="c", model="m", effort="", session_id="s"
    )
    metrics.record_event(
        "hit", execution_key="k1", client="c", model="m", effort="", session_id="s"
    )
    metrics.record_event(
        "hit", execution_key="k2", client="c", model="m", effort="", session_id="other"
    )
    assert metrics.session_event_counts("s") == {"record": 1, "hit": 1}
    assert metrics.session_event_counts("other") == {"hit": 1}
    assert metrics.session_event_counts("unknown") == {}


def test_session_events_return_full_rows_oldest_first(tmp_path):
    metrics = _metrics(tmp_path)
    metrics.record_event(
        "record", execution_key="k1", client="claude", model="sonnet", effort="", session_id="s"
    )
    metrics.record_event(
        "hit", execution_key="k1", client="claude", model="sonnet", effort="", session_id="s"
    )
    metrics.record_event(
        "record", execution_key="k2", client="openai", model="gpt-x", effort="", session_id="other"
    )
    rows = metrics.session_events("s")
    assert [(r.event, r.client, r.model, r.execution_key) for r in rows] == [
        ("record", "claude", "sonnet", "k1"),
        ("hit", "claude", "sonnet", "k1"),
    ]
    assert all(r.ts for r in rows)  # each row carries its timestamp
    assert metrics.session_events("unknown") == []
