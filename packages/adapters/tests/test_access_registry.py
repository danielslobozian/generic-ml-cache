# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for AccessRegistry — focusing on the best-effort fallback paths."""

from __future__ import annotations

import sqlite3

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec

from generic_ml_cache_adapters.adapter.outbound.metrics.access_registry import AccessRegistry
from generic_ml_cache_adapters.migration_runner import run_migrations


def _make_factory(db_path):
    def _connect():
        return sqlite3.connect(str(db_path))

    return _connect


def _registry(tmp_path) -> AccessRegistry:
    factory = _make_factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    return AccessRegistry(factory)


class _BrokenRegistry(AccessRegistry):
    """Overrides _connect so every public method exercises its except-branch."""

    def _connect(self) -> sqlite3.Connection:  # type: ignore[override]
        raise sqlite3.OperationalError("simulated I/O failure")


def _broken() -> _BrokenRegistry:
    def _factory() -> sqlite3.Connection:
        raise AssertionError("factory must not be reached in broken registry tests")

    return _BrokenRegistry(_factory)  # type: ignore[arg-type]


# --- last_access: fully uncovered by the JournalMetrics tests -----------------


def test_last_access_returns_float_timestamp_for_recorded_key(tmp_path):
    registry = _registry(tmp_path)
    registry.record(
        event="hit", match_key="execution-abc", client="claude", model="sonnet", effort=""
    )
    access_times = registry.last_access()
    assert "execution-abc" in access_times
    assert isinstance(access_times["execution-abc"], float)
    assert access_times["execution-abc"] > 0.0


def test_last_access_excludes_events_with_null_match_key(tmp_path):
    registry = _registry(tmp_path)
    registry.record(event="miss", match_key=None, client="claude", model="sonnet", effort="")
    assert registry.last_access() == {}


def test_last_access_returns_latest_timestamp_when_key_recorded_multiple_times(tmp_path):
    registry = _registry(tmp_path)
    registry.record(event="hit", match_key="key-multi", client="c", model="m", effort="")
    registry.record(event="hit", match_key="key-multi", client="c", model="m", effort="")
    access_times = registry.last_access()
    assert "key-multi" in access_times


def test_last_access_skips_rows_with_unparseable_timestamps(tmp_path):
    factory = _make_factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    conn = factory()
    conn.execute(
        "INSERT INTO access_events (ts, event, match_key, client, model, effort) "
        "VALUES ('not-a-timestamp', 'hit', 'key-bad-ts', 'c', 'm', '')"
    )
    conn.commit()
    conn.close()
    registry = AccessRegistry(factory)
    access_times = registry.last_access()
    assert "key-bad-ts" not in access_times


# --- every public method must swallow errors and return its empty fallback ----


def test_record_does_not_raise_when_registry_unavailable():
    _broken().record(event="hit", match_key="key-x", client="claude", model="sonnet", effort="")


def test_hit_counts_returns_empty_dict_when_registry_unavailable():
    assert _broken().hit_counts_by_key() == {}


def test_event_counts_returns_empty_dict_when_registry_unavailable():
    assert _broken().event_counts() == {}


def test_session_event_counts_returns_empty_dict_when_registry_unavailable():
    assert _broken().session_event_counts("session-abc") == {}


def test_session_events_returns_empty_list_when_registry_unavailable():
    assert _broken().session_events("session-abc") == []


def test_execution_keys_for_session_returns_empty_list_when_registry_unavailable():
    assert _broken().execution_keys_for_session("session-abc") == []


def test_delete_events_does_not_raise_when_registry_unavailable():
    _broken().delete_events_for_key("key-x")


def test_add_session_tag_does_not_raise_when_registry_unavailable():
    _broken().add_session_tag("session-abc", "tag-sprint3")


def test_session_tags_returns_empty_list_when_registry_unavailable():
    assert _broken().session_tags_for_id("session-abc") == []


def test_session_ids_for_tag_returns_empty_list_when_registry_unavailable():
    assert _broken().session_ids_for_tag("tag-sprint3") == []


def test_last_access_returns_none_when_registry_unavailable():
    # None (read failed) is distinct from {} (genuinely empty) so eviction can
    # tell a degraded read from an empty registry and warn accordingly (W20).
    assert _broken().last_access() is None


# --- session spec -----------------------------------------------------------


def test_set_and_retrieve_session_spec(tmp_path):
    registry = _registry(tmp_path)
    spec = SessionSpec(client="claude", model="claude-opus-4-8", effort="medium")
    registry.set_session_spec("s1", spec)
    assert registry.session_spec_for_id("s1") == spec


def test_set_session_spec_replaces_existing(tmp_path):
    registry = _registry(tmp_path)
    registry.set_session_spec("s1", SessionSpec(client="claude", model="old", effort="low"))
    new_spec = SessionSpec(client="claude", model="new", effort="high")
    registry.set_session_spec("s1", new_spec)
    assert registry.session_spec_for_id("s1") == new_spec


def test_clear_session_spec_removes_it(tmp_path):
    registry = _registry(tmp_path)
    registry.set_session_spec("s1", SessionSpec(client="claude", model="m", effort=""))
    registry.clear_session_spec("s1")
    assert registry.session_spec_for_id("s1") is None


def test_clear_session_spec_noop_when_absent(tmp_path):
    registry = _registry(tmp_path)
    registry.clear_session_spec("ghost")  # must not raise
    assert registry.session_spec_for_id("ghost") is None


def test_session_spec_for_id_returns_none_for_unknown(tmp_path):
    assert _registry(tmp_path).session_spec_for_id("no-such-session") is None


def test_set_session_spec_does_not_raise_when_unavailable():
    _broken().set_session_spec("s1", SessionSpec(client="claude", model="m", effort=""))


def test_clear_session_spec_does_not_raise_when_unavailable():
    _broken().clear_session_spec("s1")


def test_session_spec_for_id_returns_none_when_unavailable():
    assert _broken().session_spec_for_id("s1") is None
