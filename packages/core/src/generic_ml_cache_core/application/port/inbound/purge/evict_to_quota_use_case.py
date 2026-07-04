# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EvictToQuotaUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from generic_ml_cache_core.application.port.inbound.purge.evict_to_quota_command import (
    EvictToQuotaCommand,
)


class EvictToQuotaUseCase(ABC):
    """Inbound port: evict_to_quota (soft by default; hard when the command sets it)."""

    @abstractmethod
    def evict_to_quota(self, command: EvictToQuotaCommand) -> PurgeReport: ...
