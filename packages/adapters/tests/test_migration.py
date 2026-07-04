"""Tests for the migration runner."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from generic_ml_cache_core.application.port.outbound.store_migration_port import (
    CURRENT_MODEL_VERSION,
    StoreMigrationPort,
)
from generic_ml_cache_core.common.errors import MigrationFailed

from generic_ml_cache_adapters.db import DbConnection
from generic_ml_cache_adapters.migration_runner import (
    SqliteStoreMigration,
    applied_schema_version,
    run_migrations,
    schema_version,
)


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
    assert version == 5


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
    assert "idx_executions_execution_id" in indexes  # migration 0004


def test_migration_0004_adds_execution_id_column(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    conn = factory()
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(executions)").fetchall()}
    finally:
        conn.close()
    assert "execution_id" in columns


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


def test_missing_migration_file_fails_loud_at_the_last_good_version(tmp_path: Path) -> None:
    db_path = tmp_path / "gmlcache.sqlite3"
    factory = _factory(db_path)
    # Patch _CURRENT_VERSION past the shipped files so the run applies 1..5, then finds
    # no file for version 6 and fails loud with the project's MigrationFailed (§10 — the
    # StopIteration never leaks). Per-file commits mean the store lands cleanly at the
    # last successfully-applied version (5), not rolled back to 0.
    import generic_ml_cache_adapters.migration_runner as _m

    original = _m._CURRENT_VERSION
    try:
        _m._CURRENT_VERSION = 99
        with pytest.raises(MigrationFailed):
            run_migrations(factory)
    finally:
        _m._CURRENT_VERSION = original

    conn = factory()
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    finally:
        conn.close()
    assert version == 5  # the last good version, cleanly applied


def _synthetic_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, sql: str
) -> None:
    """Point the runner at a temp migrations dir holding one synthetic file (version 1)."""
    import generic_ml_cache_adapters.migration_runner as _m

    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    (migrations_dir / name).write_text(sql, encoding="utf-8")
    monkeypatch.setattr(_m, "_MIGRATIONS_DIR", migrations_dir)
    monkeypatch.setattr(_m, "_CURRENT_VERSION", 1)
    monkeypatch.setattr(_m, "_MIGRATION_IDS", (name.removesuffix(".sql"),))


def test_a_failing_migration_file_rolls_back_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The second statement fails (table already exists); the whole FILE must roll back
    # as one transaction, so the table the first statement created is gone and the
    # version is untouched — Flyway-style per-file atomicity.
    _synthetic_migration(
        tmp_path,
        monkeypatch,
        "0001.bad.sql",
        "CREATE TABLE good (x INTEGER);\nCREATE TABLE good (y INTEGER);\n",
    )
    factory = _factory(tmp_path / "db.sqlite3")
    with pytest.raises(MigrationFailed):
        run_migrations(factory)
    conn = factory()
    try:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    finally:
        conn.close()
    assert "good" not in tables  # the first statement rolled back with the file
    assert version == 0


def test_a_semicolon_inside_a_trigger_body_does_not_split_the_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A trigger body carries ';' between its statements. The old hand-split on ';'
    # would have run a broken fragment; the native executescript parses it correctly.
    _synthetic_migration(
        tmp_path,
        monkeypatch,
        "0001.trigger.sql",
        (
            "CREATE TABLE t (x INTEGER, y INTEGER);\n"
            "CREATE TRIGGER t_ai AFTER INSERT ON t BEGIN\n"
            "  UPDATE t SET y = 1 WHERE x = NEW.x;\n"
            "  UPDATE t SET y = y + 1 WHERE x = NEW.x;\n"
            "END;\n"
        ),
    )
    factory = _factory(tmp_path / "db.sqlite3")
    run_migrations(factory)  # must not raise
    conn = factory()
    try:
        triggers = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
        }
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    finally:
        conn.close()
    assert "t_ai" in triggers  # the trigger applied whole, ';' in its body and all
    assert version == 1


def test_sqlite_store_migration_is_a_store_migration_port(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    assert isinstance(SqliteStoreMigration(factory), StoreMigrationPort)


def test_sqlite_store_migration_implemented_version_matches_current_contract(
    tmp_path: Path,
) -> None:
    # The shipped adapter is always current: it implements at least what this
    # build requires, so the boot handshake passes.
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    assert SqliteStoreMigration(factory).implemented_version() >= CURRENT_MODEL_VERSION


def test_sqlite_store_migration_migrate_to_current_builds_the_schema(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    migration = SqliteStoreMigration(factory)
    migration.migrate_to_current()
    conn = factory()
    try:
        version = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    finally:
        conn.close()
    assert version == migration.implemented_version()
    # Idempotent: a second call is a no-op, never an error.
    migration.migrate_to_current()
    assert migration.applied_migrations()  # non-empty history after migrating


def test_applied_schema_version_reports_all_migrations_after_run(tmp_path: Path) -> None:
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    applied = applied_schema_version(factory)
    assert len(applied) == CURRENT_MODEL_VERSION
    assert applied[-1]["migration_id"] == "0005.execution-owned-blobs"


def test_applied_schema_version_on_an_unmigrated_db_is_empty(tmp_path: Path) -> None:
    # A DB with no schema_version table: the read-only reader reports unmigrated
    # rather than creating the table (unlike schema_version, which bootstraps it).
    factory = _factory(tmp_path / "gmlcache.sqlite3")
    assert applied_schema_version(factory) == []
