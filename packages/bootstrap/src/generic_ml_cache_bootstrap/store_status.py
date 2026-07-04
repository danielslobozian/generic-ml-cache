# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Driver-facing read-only store-status probe (W28, folds W26).

The CLI's ``gmlcache doctor`` reports the store's applied migrations. It used to do
so by handing the read-write ``sqlite_connection_factory`` to a mutating status
helper — which created the store directory, the database file, and the
``schema_version`` table as a side effect. A *status probe* must never initialize the
store it inspects (W26): a mistyped store path would silently spawn an empty store.

This hook does it read-only: an absent database file reports "unmigrated" without
touching the filesystem; a present one is opened ``mode=ro`` and read, never
created. It also keeps ``doctor`` free of any direct ``adapters`` import (W28) — the
driver depends on ``bootstrap``, ``bootstrap`` owns the wiring to ``adapters``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from generic_ml_cache_adapters.datasource import sqlite_connection_factory
from generic_ml_cache_adapters.db import DbConnection
from generic_ml_cache_adapters.migration_runner import applied_schema_version

_DB_NAME = "executions.sqlite3"


def applied_migrations(store_root: Path) -> list[dict[str, str | None]]:
    """Report the store's applied migrations without initializing it.

    Absent database file → ``[]`` (unmigrated), no filesystem touch; present → open
    the database read-only and read the applied migrations, never ``CREATE``.
    """
    db_path = Path(store_root) / _DB_NAME
    if not db_path.exists():
        return []
    factory = cast("Callable[[], DbConnection]", sqlite_connection_factory(db_path, read_only=True))
    return applied_schema_version(factory)
