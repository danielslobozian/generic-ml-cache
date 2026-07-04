# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The driver-facing read-only store-status probe (W28, folds W26).

``gmlcache doctor`` reads the applied migrations through this hook. The headline
guarantee (W26): a status probe must never initialize the store it inspects — a
mistyped path must not spawn an empty store.
"""

from pathlib import Path

from generic_ml_cache_bootstrap.persistence_backend import sqlite_persistence_backend
from generic_ml_cache_bootstrap.store_status import applied_migrations

_DB_NAME = "executions.sqlite3"


def test_absent_store_reports_unmigrated_without_creating_it(tmp_path: Path):
    assert applied_migrations(tmp_path) == []
    # W26: nothing was created — no database file, no directory contents at all.
    assert not (tmp_path / _DB_NAME).exists()
    assert list(tmp_path.iterdir()) == []


def test_reads_applied_migrations_from_a_provisioned_store(tmp_path: Path):
    sqlite_persistence_backend(tmp_path / _DB_NAME).migration.migrate_to_current()
    applied = applied_migrations(tmp_path)
    assert applied  # the store is migrated → non-empty
    assert applied[-1]["migration_id"] == "0001.initial-schema"
