# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Migration runner for the unified gmlcache database.

Tracks applied migrations in a ``schema_version`` table — one row, one integer.
Each migration **file** runs in its own transaction (Flyway-style): the runner wraps
the file — and its version bump — in one ``BEGIN``/``COMMIT`` and applies it with the
driver's native ``executescript``, which parses statement boundaries itself (a ``;``
inside a trigger or string no longer splits the file, unlike the old hand-split). A
crash mid-file rolls that file back atomically, leaving the store cleanly at the last
successfully-applied version, from which the next startup resumes. A migration file
must therefore NOT contain its own transaction control — the runner owns it.

On first use with a store that was previously managed by the PRAGMA-based runner,
the bootstrap reads ``PRAGMA user_version`` once as a fallback and seeds
``schema_version`` from it; after that PRAGMA is never touched again.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.store_migration_port import StoreMigrationPort
from generic_ml_cache_core.common.errors import MigrationFailed, StoreSchemaTooNew

from generic_ml_cache_adapters.db import DbConnection

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_CURRENT_VERSION = 1

#: Applied-migration identifiers, indexed by version number (1-based). Pre-1.0 the
#: former 0001-0005 history is compressed into a single initial schema (every schema
#: change is a full reset anyway); real per-version migrations resume at 1.0.0.
_MIGRATION_IDS = ("0001.initial-schema",)

_CREATE_VERSION_TABLE = "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"


class SqliteStoreMigration(StoreMigrationPort):
    """The shipped SQLite implementation of the store-migration contract (C-2).

    Wraps the ``run_migrations`` machinery behind the port. ``implemented_version`` is
    the highest migration this build ships (``_CURRENT_VERSION``); since bootstrap
    always runs its migrations, the shipped store is always current. The version
    handshake matters for a third-party adapter that might lag core's
    ``CURRENT_MODEL_VERSION``. The migration history for the ``doctor`` command is read
    (read-only) via :func:`applied_schema_version`, not through this port.
    """

    def __init__(
        self, conn_factory: Callable[[], DbConnection], diag: DiagnosticsPort | None = None
    ) -> None:
        self._conn_factory = conn_factory
        self._diag = diag

    def implemented_version(self) -> int:
        return _CURRENT_VERSION

    def migrate_to_current(self) -> None:
        run_migrations(self._conn_factory, self._diag)


def _migration_file(version: int) -> Path:
    """The ``.sql`` file that migrates the store to ``version``."""
    try:
        return next(_MIGRATIONS_DIR.glob(f"{version:04d}.*.sql"))
    except StopIteration as exc:
        raise MigrationFailed(f"no migration file found for version {version}") from exc


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
    except Exception:  # noqa: BLE001 — PRAGMA is SQLite-only; any DBAPI that rejects it seeds 0
        prior_version = 0
    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (prior_version,))
    conn.commit()
    return prior_version


def run_migrations(
    conn_factory: Callable[[], DbConnection],
    diag: DiagnosticsPort | None = None,
) -> None:
    """Apply any pending schema migrations to the database.

    Calling ``run_migrations`` on every startup is safe — it is a no-op when the
    schema is already at the current version.
    """
    _t = time.perf_counter()
    conn = conn_factory()
    try:
        # Rebuild-style migrations (create-with-constraints -> copy -> drop -> rename)
        # must run with foreign keys OFF (SQLite's documented table-rebuild procedure).
        # The pragma is connection-level and a no-op inside a transaction, so it is set
        # here — before any migration transaction — and persists for every file this
        # connection applies. Normal connections keep foreign_keys ON (the factory).
        conn.execute("PRAGMA foreign_keys = OFF")
        version = _bootstrap_version(conn)
        if version > _CURRENT_VERSION:
            # The store was written by a NEWER build than this one — fail loud rather
            # than treat it as up to date and write against a stale mapping (X11, the
            # mirror of the too-old-adapter PersistenceContractOutdated guard).
            raise StoreSchemaTooNew(
                f"store schema version {version} is newer than this build supports "
                f"(this build ships migrations up to version {_CURRENT_VERSION}); "
                "upgrade gmlcache to open this store"
            )
        if version == _CURRENT_VERSION:
            if diag:
                diag.debug(
                    "schema up to date",
                    version=version,
                    duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                )
            return
        if diag:
            diag.info(
                "applying schema migrations", from_version=version, to_version=_CURRENT_VERSION
            )
        for target in range(version + 1, _CURRENT_VERSION + 1):
            _apply_migration(conn, target, diag)
        if diag:
            diag.info(
                "migrations complete",
                version=_CURRENT_VERSION,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
    finally:
        conn.close()


def _apply_migration(conn: DbConnection, target: int, diag: DiagnosticsPort | None) -> None:
    """Apply one migration file atomically, bumping ``schema_version`` in the same
    transaction so the file and its version commit as a unit (Flyway per-file). A
    failure rolls this file back and translates the raw error (§10), leaving the store
    at the last good version."""
    sql_file = _migration_file(target)
    if diag:
        diag.debug("applying migration", migration=sql_file.name)
    migration_sql = sql_file.read_text(encoding="utf-8")
    try:
        # One transaction per file: executescript parses the statements natively (a
        # ';' inside a trigger/string is safe) and BEGIN..COMMIT makes the whole file
        # plus its version bump atomic. ``target`` is a trusted int from the shipped
        # migration range, never external input.
        conn.executescript(
            f"BEGIN;\n{migration_sql}\nUPDATE schema_version SET version = {target};\nCOMMIT;"  # noqa: S608 — target is a trusted int, not external input
        )
    except Exception as exc:  # noqa: BLE001 — roll this file back on ANY failure, then translate (§10)
        conn.rollback()
        if diag:
            diag.error("migration failed — rolled back", to_version=target, exc=exc)
        raise MigrationFailed(
            f"schema migration to version {target} failed and was rolled back"
        ) from exc


def applied_schema_version(
    conn_factory: Callable[[], DbConnection],
) -> list[dict[str, str]]:
    """Read the applied migrations WITHOUT initializing the store (W26) — the only
    public read of the schema history.

    It never issues the ``CREATE TABLE schema_version`` bootstrap (that lives solely in
    the migrate path, :func:`_bootstrap_version`), so it is safe on a ``mode=ro``
    connection where any write would fail. A missing ``schema_version`` table (an
    empty/uninitialized DB) or any read error reports ``[]`` (unmigrated). Used by
    the ``doctor`` status probe, which must never mutate the store it inspects.

    Each entry is ``{"migration_id": ...}``; ``schema_version`` records only the version
    integer, so no applied-at timestamp is available (X14 dropped the always-null field).
    """
    conn = conn_factory()
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        version = int(row[0]) if row is not None else 0
        return [
            {"migration_id": _MIGRATION_IDS[v - 1]}
            for v in range(1, min(version, len(_MIGRATION_IDS)) + 1)
        ]
    except Exception:  # noqa: BLE001 — missing table / read error → unmigrated
        return []
    finally:
        conn.close()
