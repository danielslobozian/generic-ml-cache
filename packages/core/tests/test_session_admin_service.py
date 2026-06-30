# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for SessionAdminService (the session-admin inbound capability)."""

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.port.inbound.session_admin.clear_session_spec_command import (
    ClearSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_command import (
    SetSessionSpecCommand,
)
from generic_ml_cache_core.application.usecase.session_admin_service import SessionAdminService


class _FakeMetrics:
    def __init__(self) -> None:
        self.specs: dict[str, SessionSpec] = {}

    def set_session_spec(self, session_id: str, spec: SessionSpec) -> None:
        self.specs[session_id] = spec

    def clear_session_spec(self, session_id: str) -> None:
        self.specs.pop(session_id, None)


def test_set_spec_stores_it():
    metrics = _FakeMetrics()
    svc = SessionAdminService(metrics)  # type: ignore[arg-type]  # duck-typed metrics
    spec = SessionSpec(client="claude", model="m", effort="")
    svc.set_spec(SetSessionSpecCommand("s1", spec))
    assert metrics.specs["s1"] is spec


def test_clear_spec_removes_it():
    metrics = _FakeMetrics()
    svc = SessionAdminService(metrics)  # type: ignore[arg-type]
    svc.set_spec(SetSessionSpecCommand("s1", SessionSpec(client="c", model="m", effort="e")))
    svc.clear_spec(ClearSessionSpecCommand("s1"))
    assert "s1" not in metrics.specs


def test_clear_unknown_session_is_a_noop():
    metrics = _FakeMetrics()
    SessionAdminService(metrics).clear_spec(ClearSessionSpecCommand("nope"))  # type: ignore[arg-type]
    assert metrics.specs == {}
