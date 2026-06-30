# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PurgeByTagUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from generic_ml_cache_core.application.port.inbound.purge.purge_by_tag_command import (
    PurgeByTagCommand,
)


class PurgeByTagUseCase(ABC):
    """Inbound port: purge_by_tag (soft by default; hard when the command sets it)."""

    @abstractmethod
    def purge_by_tag(self, command: PurgeByTagCommand) -> PurgeReport: ...
