# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Run the shipped persistence conformance TCK against the real SQLite adapter.

The same kit the in-memory fake passes (core/tests) — so the fake cannot drift from
the durable store, which is what makes the core's state-based service tests sound.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import cast

from generic_ml_cache_core.application.port.outbound.clock_port import ClockPort
from generic_ml_cache_core.testing.conformance import MlRunStoreConformance

from generic_ml_cache_adapters.adapter.outbound.persistence.sqlite.execution_repository import (
    SqliteExecutionRepository,
)
from generic_ml_cache_adapters.db import DbConnection
from generic_ml_cache_adapters.migration_runner import run_migrations


class _FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class TestSqliteStoreConformance(MlRunStoreConformance):
    def make_store(self, tmp_path):
        db_path = tmp_path / "conformance.sqlite3"

        def factory() -> DbConnection:
            return cast(DbConnection, sqlite3.connect(str(db_path)))

        run_migrations(factory)
        return SqliteExecutionRepository(factory, _FixedClock())
