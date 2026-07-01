# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the CG10 database integrity constraints (migration 0002).

Foreign keys with ON DELETE CASCADE, session-tag uniqueness, the per-connection
``PRAGMA foreign_keys = ON``, and the orphan purge the rebuild performs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from generic_ml_cache_adapters import migration_runner
from generic_ml_cache_adapters.datasource import sqlite_connection_factory
from generic_ml_cache_adapters.migration_runner import run_migrations

_INSERT_EXECUTION = (
    "INSERT INTO executions (id, execution_key, kind, state, output_persisted, created_at) "
    "VALUES (1, 'key1', 'API', 'SUCCESS', 1, '2026-06-30T00:00:00')"
)
_INSERT_ARTIFACT = (
    "INSERT INTO artifacts (execution_id, artifact_type, encoding, blob_key, size_bytes) "
    "VALUES (1, 'OUTPUT', 'utf-8', 'blob1', 3)"
)


def _migrated_factory(tmp_path: Path):
    factory = sqlite_connection_factory(tmp_path / "gmlcache.sqlite3")
    run_migrations(factory)
    return factory


def test_factory_connection_enforces_foreign_keys(tmp_path: Path) -> None:
    conn = sqlite_connection_factory(tmp_path / "gmlcache.sqlite3")()
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_delete_execution_cascades_to_children(tmp_path: Path) -> None:
    factory = _migrated_factory(tmp_path)
    conn = factory()
    try:
        conn.execute(_INSERT_EXECUTION)
        conn.execute(_INSERT_ARTIFACT)
        conn.execute("INSERT INTO token_usage (execution_id, raw_json) VALUES (1, '{}')")
        conn.execute("INSERT INTO execution_tags (execution_id, tag) VALUES (1, 'keep')")
        conn.commit()

        conn.execute("DELETE FROM executions WHERE id = 1")
        conn.commit()

        for table in ("artifacts", "token_usage", "execution_tags"):
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE execution_id = 1"  # noqa: S608 (fixed names)
            ).fetchone()[0]
            assert count == 0, f"{table} row survived its parent execution"
    finally:
        conn.close()


def test_orphan_artifact_insert_is_rejected(tmp_path: Path) -> None:
    factory = _migrated_factory(tmp_path)
    conn = factory()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(_INSERT_ARTIFACT)  # execution_id 1 has no parent row
            conn.commit()
    finally:
        conn.close()


def test_session_tags_unique_is_enforced(tmp_path: Path) -> None:
    factory = _migrated_factory(tmp_path)
    conn = factory()
    try:
        conn.execute("INSERT INTO session_tags (session_id, tag) VALUES ('s', 't')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO session_tags (session_id, tag) VALUES ('s', 't')")
            conn.commit()
    finally:
        conn.close()


def test_session_tags_insert_or_ignore_is_idempotent(tmp_path: Path) -> None:
    factory = _migrated_factory(tmp_path)
    conn = factory()
    try:
        conn.execute("INSERT OR IGNORE INTO session_tags (session_id, tag) VALUES ('s', 't')")
        conn.execute("INSERT OR IGNORE INTO session_tags (session_id, tag) VALUES ('s', 't')")
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM session_tags WHERE session_id = 's' AND tag = 't'"
        ).fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_migration_0002_purges_pre_existing_orphans(tmp_path: Path) -> None:
    db_path = tmp_path / "gmlcache.sqlite3"
    # Build a version-1 database (pre-FK) holding an orphan artifact + a duplicate
    # session tag — the shape a released 0.x store could carry.
    raw = sqlite3.connect(str(db_path))
    try:
        schema_0001 = (migration_runner._MIGRATIONS_DIR / "0001.unified-schema.sql").read_text(
            encoding="utf-8"
        )
        raw.executescript(schema_0001)
        raw.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        raw.execute("INSERT INTO schema_version (version) VALUES (1)")
        raw.execute(
            "INSERT INTO artifacts (execution_id, artifact_type, encoding, blob_key, size_bytes) "
            "VALUES (999, 'OUTPUT', 'utf-8', 'orphan', 1)"
        )
        raw.execute("INSERT INTO session_tags (session_id, tag) VALUES ('s', 'dup')")
        raw.execute("INSERT INTO session_tags (session_id, tag) VALUES ('s', 'dup')")
        raw.commit()
    finally:
        raw.close()

    run_migrations(sqlite_connection_factory(db_path))

    conn = sqlite_connection_factory(db_path)()
    try:
        orphans = conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE execution_id = 999"
        ).fetchone()[0]
        dup_tags = conn.execute(
            "SELECT COUNT(*) FROM session_tags WHERE session_id = 's' AND tag = 'dup'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert orphans == 0  # the FK-checked rebuild dropped the parentless artifact
    assert dup_tags == 1  # the UNIQUE rebuild collapsed the duplicate session tag
