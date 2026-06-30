# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EvictStaleUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from generic_ml_cache_core.application.port.inbound.purge.evict_stale_command import (
    EvictStaleCommand,
)


class EvictStaleUseCase(ABC):
    """Inbound port: evict_stale (soft by default; hard when the command sets it)."""

    @abstractmethod
    def evict_stale(self, command: EvictStaleCommand) -> PurgeReport: ...
