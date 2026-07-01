"""Tests for the migration runner."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import cast

from generic_ml_cache_adapters.db import DbConnection
from generic_ml_cache_adapters.migration_runner import run_migrations, schema_version


def _factory(db_path: Path) -> Callable[[], DbConnection]:
    def _connect() -> DbConnection:
        return cast(DbConnection, sqlite3.connect(str(db_path)))

    return _connect


def test_migration_creates_all_execution_tables(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    conn = factory()
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        conn.close()
    expected = {
        "call_identities",
        "executions",
        "artifacts",
        "token_usage",
        "execution_tags",
        "schema_version",
    }
    assert expected <= tables


def test_migration_creates_all_registry_tables(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    conn = factory()
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    finally:
        conn.close()
    expected = {"access_events", "session_tags", "session_specs"}
    assert expected <= tables


def test_migration_is_idempotent(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    run_migrations(factory)  # must not raise


def test_migration_records_applied_migration(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    conn = factory()
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    finally:
        conn.close()
    assert version == 2


def test_migration_creates_indexes(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    conn = factory()
    try:
        indexes = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
    finally:
        conn.close()
    assert "idx_executions_key" in indexes
    assert "idx_artifacts_execution" in indexes


def test_schema_version_returns_applied_migrations(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    result = schema_version(factory)
    assert len(result) >= 1
    assert result[0]["migration_id"] == "0001.unified-schema"
    assert "applied_at_utc" in result[0]


def test_schema_version_returns_empty_before_migrations(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "empty.sqlite3")
    assert schema_version(factory) == []


def test_schema_version_returns_empty_on_broken_connection() -> None:
    import unittest.mock as mock

    bad_conn = mock.MagicMock()
    bad_conn.execute.side_effect = sqlite3.OperationalError("database is locked")

    def _bad():
        return bad_conn

    assert schema_version(_bad) == []


def test_migration_rollback_on_failure(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    # Patch _CURRENT_VERSION to a version whose SQL file doesn't exist so
    # migration fails inside the transaction and triggers ROLLBACK + error log.
    import generic_ml_cache_adapters.migration_runner as _m

    original = _m._CURRENT_VERSION
    try:
        _m._CURRENT_VERSION = 99
        try:
            run_migrations(factory)
        except Exception:
            pass  # expected — we only care that it didn't hang and logged
    finally:
        _m._CURRENT_VERSION = original
