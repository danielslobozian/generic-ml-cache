# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for SessionReportService (the session-report inbound capability)."""

from generic_ml_cache_core.application.port.inbound.session_report.report_for_session_command import (
    ReportForSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_report.report_for_tag_command import (
    ReportForTagCommand,
)
from generic_ml_cache_core.application.port.out.metrics_port import SessionEventRow
from generic_ml_cache_core.application.usecase.session_report_service import SessionReportService


def _event(execution_key="k1", event="record"):
    return SessionEventRow(
        ts="2026-01-01T09:00:00",
        event=event,
        client="claude",
        model="m",
        execution_key=execution_key,
    )


class _FakeMetrics:
    def __init__(self, events_by_session, ids_by_tag):
        self._events = events_by_session
        self._ids = ids_by_tag

    def session_events(self, session_id):
        return self._events.get(session_id, [])

    def session_ids_for_tag(self, tag):
        return self._ids.get(tag, [])


class _FakeRepo:
    def find_current(self, execution_key):
        return None  # no token usage available — the report counts it as unknown


def test_report_for_session_counts_events():
    svc = SessionReportService(  # type: ignore[arg-type]  # duck-typed ports
        _FakeMetrics({"s1": [_event(), _event(event="hit")]}, {}), _FakeRepo()
    )
    report = svc.report_for_session(ReportForSessionCommand("s1"))
    assert report.session_id == "s1"
    assert report.invocations == 2
    assert report.executions == 1
    assert report.hits == 1


def test_report_for_session_unknown_session_is_empty():
    svc = SessionReportService(_FakeMetrics({}, {}), _FakeRepo())  # type: ignore[arg-type]
    report = svc.report_for_session(ReportForSessionCommand("nope"))
    assert report.invocations == 0


def test_report_for_tag_merges_sessions():
    metrics = _FakeMetrics(
        {"s1": [_event()], "s2": [_event(), _event()]},
        {"t": ["s1", "s2"]},
    )
    svc = SessionReportService(metrics, _FakeRepo())  # type: ignore[arg-type]
    result = svc.report_for_tag(ReportForTagCommand("t"))
    assert result.tag == "t"
    assert result.session_count == 2
    assert result.report.invocations == 3


def test_report_for_tag_no_sessions():
    svc = SessionReportService(_FakeMetrics({}, {}), _FakeRepo())  # type: ignore[arg-type]
    result = svc.report_for_tag(ReportForTagCommand("missing"))
    assert result.session_count == 0
    assert result.report.invocations == 0
