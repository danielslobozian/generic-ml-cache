# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Run the shipped persistence conformance TCK against the in-memory reference fake."""

from __future__ import annotations

from datetime import datetime, timezone

from generic_ml_cache_core.application.port.outbound.clock_port import ClockPort
from generic_ml_cache_core.testing.conformance import MlRunStoreConformance
from generic_ml_cache_core.testing.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)


class _FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class TestInMemoryStoreConformance(MlRunStoreConformance):
    def make_store(self, tmp_path):
        return InMemoryExecutionRepository(_FixedClock())
