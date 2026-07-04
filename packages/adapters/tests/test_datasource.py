# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for sqlite_connection_factory."""

from __future__ import annotations

from generic_ml_cache_adapters.datasource import sqlite_connection_factory


def test_factory_returns_callable(tmp_path):
    factory = sqlite_connection_factory(tmp_path / "test.sqlite3")
    assert callable(factory)


def test_factory_opens_a_working_connection(tmp_path):
    factory = sqlite_connection_factory(tmp_path / "test.sqlite3")
    conn = factory()
    try:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        assert conn.execute("SELECT x FROM t").fetchone()[0] == 1
    finally:
        conn.close()


def test_factory_creates_parent_directories(tmp_path):
    db_path = tmp_path / "a" / "b" / "c" / "test.sqlite3"
    factory = sqlite_connection_factory(db_path)
    conn = factory()
    conn.close()
    assert db_path.exists()


def test_factory_each_call_returns_independent_connection(tmp_path):
    factory = sqlite_connection_factory(tmp_path / "test.sqlite3")
    c1 = factory()
    c2 = factory()
    try:
        assert c1 is not c2
    finally:
        c1.close()
        c2.close()


def test_factory_enables_wal_and_busy_timeout(tmp_path):
    factory = sqlite_connection_factory(tmp_path / "test.sqlite3")
    conn = factory()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()


def test_check_same_thread_false_allows_cross_thread_use(tmp_path):
    import threading

    factory = sqlite_connection_factory(tmp_path / "test.sqlite3", check_same_thread=False)
    conn = factory()
    errors = []

    def _use():
        try:
            conn.execute("SELECT 1")
        except Exception as e:
            errors.append(e)

    t = threading.Thread(target=_use)
    t.start()
    t.join()
    conn.close()
    assert not errors
