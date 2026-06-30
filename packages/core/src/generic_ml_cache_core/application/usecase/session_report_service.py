# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SessionReportService — the session-report capability.

Relocates the event -> token-usage aggregation that the CLI and daemon
controllers each duplicated into one place behind inbound ports: gather a
session's (or a tag's) journal events, join each to its current execution's
usage, and project the roll-up via the pure ``build_session_report``.
"""

from __future__ import annotations

from collections.abc import Iterable

from generic_ml_cache_core.application.domain.model.session.session_report import (
    SessionReport,
    TagSessionReport,
)
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.inbound.session_report.report_for_session_command import (
    ReportForSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_report.report_for_session_use_case import (
    ReportForSessionUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_report.report_for_tag_command import (
    ReportForTagCommand,
)
from generic_ml_cache_core.application.port.inbound.session_report.report_for_tag_use_case import (
    ReportForTagUseCase,
)
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort, SessionEventRow
from generic_ml_cache_core.application.usecase.session_report import build_session_report


class SessionReportService(ReportForSessionUseCase, ReportForTagUseCase):
    """Report on one session, or on every session carrying a tag."""

    def __init__(self, metrics: MetricsPort, repository: ExecutionRepositoryPort) -> None:
        self._metrics = metrics
        self._repository = repository

    def report_for_session(self, command: ReportForSessionCommand) -> SessionReport:
        events = self._metrics.session_events(command.session_id)
        return build_session_report(command.session_id, events, self._usage_by_key(events))

    def report_for_tag(self, command: ReportForTagCommand) -> TagSessionReport:
        session_ids = self._metrics.session_ids_for_tag(command.tag)
        events: list[SessionEventRow] = []
        for session_id in session_ids:
            events.extend(self._metrics.session_events(session_id))
        report = build_session_report(command.tag, events, self._usage_by_key(events))
        return TagSessionReport(tag=command.tag, report=report, session_count=len(session_ids))

    def _usage_by_key(self, events: Iterable[SessionEventRow]) -> dict[str, TokenUsage]:
        usage_by_key: dict[str, TokenUsage] = {}
        for key in {e.execution_key for e in events if e.execution_key}:
            execution = self._repository.find_current(key)
            if execution is not None and execution.token_usage is not None:
                usage_by_key[key] = execution.token_usage
        return usage_by_key
