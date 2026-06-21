# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ProbeUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.probe.probe_report import ProbeReport
from generic_ml_cache_core.application.port.inbound.probe_command import ProbeCommand


class ProbeUseCase(ABC):
    """Inbound port for the read-only cache probe — a forecast of what a run would
    do, with no side effects (no client launch, no store, no journal event)."""

    @abstractmethod
    def execute(self, command: ProbeCommand) -> ProbeReport:
        """Forecast the verdict for ``command`` without running or recording."""
