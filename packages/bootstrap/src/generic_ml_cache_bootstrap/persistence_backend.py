# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PersistenceBackend — the DB-backed outbound adapters, bundled as one unit (V33).

The repository, the call journal, and the migration adapter all share ONE database
through ONE connection FACTORY (each operation opens its own connection from it), so
they are an atomic unit — you cannot have a Postgres repository and a SQLite journal
"for the same store". Grouping them into a single injected bundle kills the bare
``conn_factory`` seam that C-1 exposed: once the dialect layer is gone, a free
connection factory is a *crossable* seam (a Postgres factory handed to SQLite-dialect
adapters explodes at runtime). Here the connection factory is owned by / constructed
with the dialect adapters, never handed across.

The bundle is composition plumbing, NOT a hexagonal port: it is a frozen dataclass
of the individual core outbound ports (the same shape as ``ApplicationApi`` on the
inbound side). Core still owns and injects each port one by one — the core never
sees a "backend"; the bundle exists only at composition time. Both the bundle type
and the shipped ``sqlite_persistence_backend`` factory live here in bootstrap
(never in adapters — a factory in adapters returning a bootstrap type would invert
``adapters ──▶ bootstrap``); adapters ship only the leaf classes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from generic_ml_cache_adapters.adapter.outbound.clock.system_clock import SystemClock
from generic_ml_cache_adapters.adapter.outbound.metrics.access_registry import AccessRegistry
from generic_ml_cache_adapters.adapter.outbound.metrics.journal_metrics import JournalMetrics
from generic_ml_cache_adapters.adapter.outbound.persistence.sqlite.execution_repository import (
    SqliteExecutionRepository,
)
from generic_ml_cache_adapters.datasource import sqlite_connection_factory
from generic_ml_cache_adapters.db import DbConnection
from generic_ml_cache_adapters.migration_runner import SqliteStoreMigration
from generic_ml_cache_core.application.port.outbound.call_journal_ports import (
    CallStatsPort,
    PurgeJournalPort,
    RecordCallEventPort,
    SessionQueryPort,
    SessionReportSourcePort,
    SessionSpecPort,
    SessionTagsPort,
)
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.ml_run_ports import (
    AnnotateMlRunPort,
    InspectMlRunsPort,
    PurgeMlRunsPort,
    ReadMlRunPort,
    SaveMlRunPort,
)
from generic_ml_cache_core.application.port.outbound.repair_ml_runs_port import RepairMlRunsPort
from generic_ml_cache_core.application.port.outbound.store_migration_port import StoreMigrationPort


@dataclass(frozen=True)
class PersistenceBackend:
    """The DB-backed outbound ports, grouped so they share one datasource.

    One field per outbound port the use-case graph consumes (mirrors ApplicationApi
    on the inbound side). The shipped ``sqlite_persistence_backend`` binds one
    ``SqliteExecutionRepository`` instance to every ``*_ml_run(s)`` field and one
    ``JournalMetrics`` instance to every journal field — one impl, many role ports
    (V32/B-1). An embedder replacing the DB implements these ports over their own
    store and packs their own backend.
    """

    # the execution repository's role ports
    save_ml_run: SaveMlRunPort
    read_ml_run: ReadMlRunPort
    annotate_ml_run: AnnotateMlRunPort
    inspect_ml_runs: InspectMlRunsPort
    purge_ml_runs: PurgeMlRunsPort
    repair_ml_runs: RepairMlRunsPort
    # the call journal's role ports
    record_call_event: RecordCallEventPort
    call_stats: CallStatsPort
    session_report_source: SessionReportSourcePort
    session_query: SessionQueryPort
    purge_journal: PurgeJournalPort
    session_tags: SessionTagsPort
    session_spec: SessionSpecPort
    # the whole-store migration contract
    migration: StoreMigrationPort


def sqlite_persistence_backend(
    db_path: Path,
    diag: DiagnosticsPort | None = None,
    *,
    check_same_thread: bool = True,
) -> PersistenceBackend:
    """The shipped SQLite persistence backend: repository + journal + migration over
    one SQLite connection factory (owned here, never exposed).

    ``check_same_thread=False`` for a multi-threaded driver (the daemon's async pool);
    the default single-threaded ``True`` suits the CLI. The clock is internal — only
    the repository uses it (to stamp supersession / ``persisted_at``)."""
    conn_factory = cast(
        "Callable[[], DbConnection]",
        sqlite_connection_factory(db_path, check_same_thread=check_same_thread),
    )
    clock = SystemClock()
    repository = SqliteExecutionRepository(conn_factory, clock)
    journal = JournalMetrics(AccessRegistry(conn_factory, diag=diag))
    # store_root = the DB's directory, holding ``store.lock`` — lets the migration run
    # under the blocking-exclusive store lock so a concurrent first-init is serialized
    # (Y1) rather than racing to double-seed schema_version or collide on the DDL.
    migration = SqliteStoreMigration(conn_factory, diag, store_root=db_path.parent)
    return PersistenceBackend(
        save_ml_run=repository,
        read_ml_run=repository,
        annotate_ml_run=repository,
        inspect_ml_runs=repository,
        purge_ml_runs=repository,
        repair_ml_runs=repository,
        record_call_event=journal,
        call_stats=journal,
        session_report_source=journal,
        session_query=journal,
        purge_journal=journal,
        session_tags=journal,
        session_spec=journal,
        migration=migration,
    )
