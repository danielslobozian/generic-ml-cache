# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Migration runner for the unified gmlcache database.

Tracks applied migrations in a ``schema_version`` table — one row, one integer.
Each migration runs atomically inside a BEGIN / COMMIT block: a crash mid-migration
leaves the version unchanged so the next startup retries from a clean slate.

On first use with a store that was previously managed by the PRAGMA-based runner,
the bootstrap reads ``PRAGMA user_version`` once as a fallback and seeds
``schema_version`` from it; after that PRAGMA is never touched again.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional

from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.common.db import DbConnection

from generic_ml_cache_adapters.adapter.out.diagnostics.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_CURRENT_VERSION = 1

_CREATE_VERSION_TABLE = "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"


def _iter_statements(sql: str):
    """Yield non-empty SQL statements, stripping line comments."""
    for block in sql.split(";"):
        lines = [ln for ln in block.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            yield stmt


def _bootstrap_version(conn: DbConnection) -> int:
    """Ensure schema_version exists and return the current version.

    If the table is absent or empty, reads ``PRAGMA user_version`` as a one-time
    fallback for stores migrated by the old runner, then seeds the table.
    """
    conn.execute(_CREATE_VERSION_TABLE)
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    if row is not None:
        return int(row[0])
    # First run or upgrade from PRAGMA-based runner: seed from PRAGMA (SQLite only)
    # or default to 0. PRAGMA is sent as a plain SQL string — no sqlite3 import needed.
    try:
        pragma_row = conn.execute("PRAGMA user_version").fetchone()
        prior_version = int(pragma_row[0]) if pragma_row is not None else 0
    except Exception:
        prior_version = 0
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (prior_version,))
    conn.commit()
    return prior_version


def run_migrations(
    conn_factory: Callable[[], DbConnection],
    diag: Optional[DiagnosticsPort] = None,
) -> None:
    """Apply any pending schema migrations to the database.

    Calling ``run_migrations`` on every startup is safe — it is a no-op when the
    schema is already at the current version.
    """
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    conn = conn_factory()
    try:
        version = _bootstrap_version(conn)
        if version >= _CURRENT_VERSION:
            _diag.debug(
                "schema up to date",
                version=version,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
            return
        _diag.info(
            "applying schema migrations",
            from_version=version,
            to_version=_CURRENT_VERSION,
        )
        conn.execute("BEGIN")
        try:
            for v in range(version + 1, _CURRENT_VERSION + 1):
                sql_file = next(_MIGRATIONS_DIR.glob(f"{v:04d}.*.sql"))
                _diag.debug("applying migration", migration=sql_file.name)
                for stmt in _iter_statements(sql_file.read_text(encoding="utf-8")):
                    conn.execute(stmt)
                conn.execute("UPDATE schema_version SET version = ?", (v,))
            conn.execute("COMMIT")
            _diag.info(
                "migrations complete",
                version=_CURRENT_VERSION,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        except Exception as exc:
            conn.execute("ROLLBACK")
            _diag.error(
                "migration failed — rolled back",
                from_version=version,
                exc=exc,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
            raise
    finally:
        conn.close()


def schema_version(
    conn_factory: Callable[[], DbConnection], diag: Optional[DiagnosticsPort] = None
) -> List[dict]:
    """Return the current schema version as a list, or ``[]`` if unmigrated."""
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    _diag.debug("schema-version ENTER")
    conn = conn_factory()
    try:
        conn.execute(_CREATE_VERSION_TABLE)
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        version = int(row[0]) if row is not None else 0
        result = (
            []
            if version == 0
            else [{"migration_id": "0001.unified-schema", "applied_at_utc": None}]
        )
        _diag.debug(
            "schema-version EXIT",
            version=version,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
        return result
    except Exception as exc:
        _diag.error(
            "schema-version FAILED",
            exc=exc,
            duration_ms=round((time.perf_counter() - _t) * 1000, 1),
        )
        return []
    finally:
        conn.close()
