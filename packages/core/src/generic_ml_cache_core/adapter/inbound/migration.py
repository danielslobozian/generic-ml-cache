# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Migration runner for the unified gmlcache database.

The migration files live under ``generic_ml_cache_core/migrations/`` and are
applied in filename order by yoyo-migrations. yoyo tracks applied migrations
in its own ``_yoyo_migration`` table so the runner is idempotent — safe to
call on every startup.
"""

from __future__ import annotations

from pathlib import Path
from sqlite3 import Connection
from typing import Callable, List

import yoyo

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


def run_migrations(conn_factory: Callable[[], Connection]) -> None:
    """Apply any pending schema migrations to the database.

    Opens a transient connection via *conn_factory* solely to obtain the
    database file path, then delegates to yoyo for ordered, idempotent DDL
    execution. The *conn_factory* must reference a file-backed SQLite
    database; in-memory databases are not supported.
    """
    conn = conn_factory()
    try:
        row = conn.execute("PRAGMA database_list").fetchone()
        db_file: str = row[2]
    finally:
        conn.close()

    if not db_file:
        raise ValueError(
            "run_migrations requires a file-backed SQLite database; "
            "in-memory (':memory:') databases are not supported."
        )

    backend = yoyo.get_backend(f"sqlite:///{db_file}")
    try:
        migrations = yoyo.read_migrations(str(_MIGRATIONS_DIR))
        with backend.lock():
            backend.apply_migrations(backend.to_apply(migrations))
    finally:
        backend.connection.close()


def schema_version(conn_factory: Callable[[], Connection]) -> List[dict]:
    """Return applied migrations in order, or an empty list if the store has no schema yet."""
    conn = conn_factory()
    try:
        rows = conn.execute(
            "SELECT migration_id, applied_at_utc"
            " FROM _yoyo_migration ORDER BY applied_at_utc"
        ).fetchall()
        return [{"migration_id": row[0], "applied_at_utc": row[1]} for row in rows]
    except Exception:
        return []
    finally:
        conn.close()
