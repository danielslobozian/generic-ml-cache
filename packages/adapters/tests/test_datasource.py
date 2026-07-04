# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for sqlite_connection_factory."""

from __future__ import annotations

import sqlite3

import pytest
from generic_ml_cache_core.common.errors import StoreUnavailable

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


def test_unopenable_db_raises_store_unavailable(tmp_path):
    # The parent path is a FILE, so mkdir/connect cannot create the DB there — a
    # hard outage. It must surface as StoreUnavailable, never a raw sqlite3/OS error.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a directory")
    factory = sqlite_connection_factory(blocker / "sub" / "db.sqlite3")
    with pytest.raises(StoreUnavailable):
        factory()


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


def test_read_only_factory_reads_committed_data_but_rejects_writes(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    rw = sqlite_connection_factory(db_path)
    conn = rw()
    try:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (7)")
        conn.commit()
    finally:
        conn.close()

    conn = sqlite_connection_factory(db_path, read_only=True)()
    try:
        assert conn.execute("SELECT x FROM t").fetchone()[0] == 7
        with pytest.raises(sqlite3.OperationalError):  # readonly database
            conn.execute("INSERT INTO t VALUES (8)")
    finally:
        conn.close()


def test_read_only_factory_never_creates_a_missing_db(tmp_path):
    db_path = tmp_path / "absent.sqlite3"
    factory = sqlite_connection_factory(db_path, read_only=True)
    with pytest.raises(StoreUnavailable):
        factory()
    assert not db_path.exists()  # mode=ro must not create the file


def test_read_only_factory_opens_a_path_containing_a_question_mark(tmp_path):
    # X22: a '?' (or '#') is valid on disk but special in SQLite URI syntax; the
    # read-only URI must percent-encode the path so it opens the right file instead
    # of mis-parsing 'abc.sqlite3' as a query and reporting the store as unmigrated.
    db_path = tmp_path / "store?abc.sqlite3"
    conn = sqlite_connection_factory(db_path)()
    try:
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (42)")
        conn.commit()
    finally:
        conn.close()

    conn = sqlite_connection_factory(db_path, read_only=True)()
    try:
        assert conn.execute("SELECT x FROM t").fetchone()[0] == 42  # the real file, not a new one
    finally:
        conn.close()
