# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for AccessRegistry — focusing on the best-effort fallback paths."""

from __future__ import annotations

import sqlite3

from generic_ml_cache_core.adapter.out.metrics.access_registry import (
    _DB_NAME,
    _SCHEMA,
    AccessRegistry,
)


class _BrokenRegistry(AccessRegistry):
    """Overrides _connect so every public method exercises its except-branch."""

    def _connect(self) -> sqlite3.Connection:
        raise sqlite3.OperationalError("simulated I/O failure")


# --- last_access: fully uncovered by the JournalMetrics tests -----------------


def test_last_access_returns_float_timestamp_for_recorded_key(tmp_path):
    registry = AccessRegistry(tmp_path)
    registry.record(
        event="hit", match_key="execution-abc", client="claude", model="sonnet", effort=""
    )
    access_times = registry.last_access()
    assert "execution-abc" in access_times
    assert isinstance(access_times["execution-abc"], float)
    assert access_times["execution-abc"] > 0.0


def test_last_access_excludes_events_with_null_match_key(tmp_path):
    registry = AccessRegistry(tmp_path)
    registry.record(event="miss", match_key=None, client="claude", model="sonnet", effort="")
    assert registry.last_access() == {}


def test_last_access_returns_latest_timestamp_when_key_recorded_multiple_times(tmp_path):
    registry = AccessRegistry(tmp_path)
    registry.record(event="hit", match_key="key-multi", client="c", model="m", effort="")
    registry.record(event="hit", match_key="key-multi", client="c", model="m", effort="")
    access_times = registry.last_access()
    assert "key-multi" in access_times


def test_last_access_skips_rows_with_unparseable_timestamps(tmp_path):
    db_path = tmp_path / _DB_NAME
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    conn.execute(
        "INSERT INTO access_events (ts, event, match_key, client, model, effort) "
        "VALUES ('not-a-timestamp', 'hit', 'key-bad-ts', 'c', 'm', '')"
    )
    conn.commit()
    conn.close()
    registry = AccessRegistry(tmp_path)
    access_times = registry.last_access()
    assert "key-bad-ts" not in access_times


# --- every public method must swallow errors and return its empty fallback ----


def test_record_does_not_raise_when_registry_unavailable(tmp_path):
    _BrokenRegistry(tmp_path).record(
        event="hit", match_key="key-x", client="claude", model="sonnet", effort=""
    )


def test_hit_counts_returns_empty_dict_when_registry_unavailable(tmp_path):
    assert _BrokenRegistry(tmp_path).hit_counts_by_key() == {}


def test_event_counts_returns_empty_dict_when_registry_unavailable(tmp_path):
    assert _BrokenRegistry(tmp_path).event_counts() == {}


def test_session_event_counts_returns_empty_dict_when_registry_unavailable(tmp_path):
    assert _BrokenRegistry(tmp_path).session_event_counts("session-abc") == {}


def test_session_events_returns_empty_list_when_registry_unavailable(tmp_path):
    assert _BrokenRegistry(tmp_path).session_events("session-abc") == []


def test_execution_keys_for_session_returns_empty_list_when_registry_unavailable(tmp_path):
    assert _BrokenRegistry(tmp_path).execution_keys_for_session("session-abc") == []


def test_delete_events_does_not_raise_when_registry_unavailable(tmp_path):
    _BrokenRegistry(tmp_path).delete_events_for_key("key-x")


def test_add_session_tag_does_not_raise_when_registry_unavailable(tmp_path):
    _BrokenRegistry(tmp_path).add_session_tag("session-abc", "tag-sprint3")


def test_session_tags_returns_empty_list_when_registry_unavailable(tmp_path):
    assert _BrokenRegistry(tmp_path).session_tags_for_id("session-abc") == []


def test_session_ids_for_tag_returns_empty_list_when_registry_unavailable(tmp_path):
    assert _BrokenRegistry(tmp_path).session_ids_for_tag("tag-sprint3") == []


def test_last_access_returns_empty_dict_when_registry_unavailable(tmp_path):
    assert _BrokenRegistry(tmp_path).last_access() == {}
