# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ReportForSessionUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.session.session_report import SessionReport
from generic_ml_cache_core.application.port.inbound.session_report.report_for_session_command import (
    ReportForSessionCommand,
)


class ReportForSessionUseCase(ABC):
    """Inbound port: roll up one session's activity into a SessionReport."""

    @abstractmethod
    def report_for_session(self, command: ReportForSessionCommand) -> SessionReport: ...
