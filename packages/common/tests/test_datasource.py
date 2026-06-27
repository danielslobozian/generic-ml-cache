import sqlite3
from pathlib import Path

import pytest

from generic_ml_cache_common.datasource import sqlite_connection_factory


def test_factory_returns_callable(tmp_path: Path) -> None:
    factory = sqlite_connection_factory(tmp_path / "test.db")
    assert callable(factory)


def test_factory_opens_connection(tmp_path: Path) -> None:
    factory = sqlite_connection_factory(tmp_path / "test.db")
    conn = factory()
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_factory_creates_parent_directory(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "test.db"
    factory = sqlite_connection_factory(db_path)
    conn = factory()
    conn.close()
    assert db_path.exists()


def test_factory_returns_independent_connections(tmp_path: Path) -> None:
    factory = sqlite_connection_factory(tmp_path / "test.db")
    conn1 = factory()
    conn2 = factory()
    try:
        assert conn1 is not conn2
    finally:
        conn1.close()
        conn2.close()


def test_check_same_thread_false_does_not_raise(tmp_path: Path) -> None:
    factory = sqlite_connection_factory(tmp_path / "test.db", check_same_thread=False)
    conn = factory()
    conn.close()


def test_connection_is_usable(tmp_path: Path) -> None:
    factory = sqlite_connection_factory(tmp_path / "test.db")
    conn = factory()
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        row = conn.execute("SELECT id FROM t").fetchone()
        assert row == (1,)
    finally:
        conn.close()
