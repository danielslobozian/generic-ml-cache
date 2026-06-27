# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Migration runner for the unified gmlcache database.

Tracks applied migrations with SQLite's built-in ``PRAGMA user_version``.
Each migration is applied atomically inside a single BEGIN EXCLUSIVE / COMMIT
block: a crash mid-migration leaves the version unchanged so the next startup
retries from a clean slate. No network calls, no external tracking tables.
"""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection
from typing import Callable, List

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"
_CURRENT_VERSION = 1


def _iter_statements(sql: str):
    """Yield non-empty SQL statements, stripping line comments."""
    for block in sql.split(";"):
        lines = [ln for ln in block.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            yield stmt


def run_migrations(conn_factory: Callable[[], Connection]) -> None:
    """Apply any pending schema migrations to the database.

    The *conn_factory* must reference a file-backed SQLite database; calling
    ``run_migrations`` on every startup is safe — it is a no-op when the
    schema is already at the current version.
    """
    conn = conn_factory()
    conn.isolation_level = None  # explicit transaction control; no implicit BEGIN
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= _CURRENT_VERSION:
            return
        conn.execute("BEGIN EXCLUSIVE")
        try:
            for v in range(version + 1, _CURRENT_VERSION + 1):
                sql_file = next(_MIGRATIONS_DIR.glob(f"{v:04d}.*.sql"))
                for stmt in _iter_statements(sql_file.read_text(encoding="utf-8")):
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version = {v}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def schema_version(conn_factory: Callable[[], Connection]) -> List[dict]:
    """Return the current schema version as a list, or ``[]`` if unmigrated."""
    conn = conn_factory()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            return []
        return [{"migration_id": "0001.unified-schema", "applied_at_utc": None}]
    except Exception:
        return []
    finally:
        conn.close()
