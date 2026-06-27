# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Migration runner for the unified gmlcache database.

Tracks applied migrations with SQLite's built-in ``PRAGMA user_version``.
Each migration is applied atomically inside a single BEGIN EXCLUSIVE / COMMIT
block: a crash mid-migration leaves the version unchanged so the next startup
retries from a clean slate. No network calls, no external tracking tables.
"""

from __future__ import annotations

import time
from pathlib import Path
from sqlite3 import Connection
from typing import Callable, List, Optional

from generic_ml_cache_core.application.port.out.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort

_MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"
_CURRENT_VERSION = 1


def _iter_statements(sql: str):
    """Yield non-empty SQL statements, stripping line comments."""
    for block in sql.split(";"):
        lines = [ln for ln in block.splitlines() if not ln.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            yield stmt


def run_migrations(
    conn_factory: Callable[[], Connection],
    diag: Optional[DiagnosticsPort] = None,
) -> None:
    """Apply any pending schema migrations to the database.

    The *conn_factory* must reference a file-backed SQLite database; calling
    ``run_migrations`` on every startup is safe — it is a no-op when the
    schema is already at the current version.
    """
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    conn = conn_factory()
    conn.isolation_level = None  # explicit transaction control; no implicit BEGIN
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
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
        conn.execute("BEGIN EXCLUSIVE")
        try:
            for v in range(version + 1, _CURRENT_VERSION + 1):
                sql_file = next(_MIGRATIONS_DIR.glob(f"{v:04d}.*.sql"))
                _diag.debug("applying migration", migration=sql_file.name)
                for stmt in _iter_statements(sql_file.read_text(encoding="utf-8")):
                    conn.execute(stmt)
                conn.execute(f"PRAGMA user_version = {v}")
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
    conn_factory: Callable[[], Connection], diag: Optional[DiagnosticsPort] = None
) -> List[dict]:
    """Return the current schema version as a list, or ``[]`` if unmigrated."""
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _t = time.perf_counter()
    _diag.debug("schema-version ENTER")
    conn = conn_factory()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
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
