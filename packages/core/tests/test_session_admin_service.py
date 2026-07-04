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

    def session_spec(self, session_id: str) -> SessionSpec | None:
        return self.specs.get(session_id)

    def list_session_ids(self) -> list[str]:
        return sorted(self.specs)

    def session_ids_for_tag(self, tag: str) -> list[str]:
        return ["s1", "s2"] if tag == "t" else []

    def execution_keys_for_session(self, session_id: str) -> list[str]:
        return {"s1": ["k1", "k2"], "s2": ["k3"]}.get(session_id, [])


def test_set_spec_stores_it():
    metrics = _FakeMetrics()
    svc = SessionAdminService(metrics, metrics)  # type: ignore[arg-type]  # duck-typed metrics
    spec = SessionSpec(client="claude", model="m", effort="")
    svc.set_spec(SetSessionSpecCommand("s1", spec))
    assert metrics.specs["s1"] is spec


def test_clear_spec_removes_it():
    metrics = _FakeMetrics()
    svc = SessionAdminService(metrics, metrics)  # type: ignore[arg-type]
    svc.set_spec(SetSessionSpecCommand("s1", SessionSpec(client="c", model="m", effort="e")))
    svc.clear_spec(ClearSessionSpecCommand("s1"))
    assert "s1" not in metrics.specs


def test_get_spec_returns_the_stored_spec_or_none():
    from generic_ml_cache_core.application.port.inbound.session_admin.get_session_spec_command import (
        GetSessionSpecCommand,
    )

    metrics = _FakeMetrics()
    svc = SessionAdminService(metrics, metrics)  # type: ignore[arg-type]
    spec = SessionSpec(client="c", model="m", effort="e")
    svc.set_spec(SetSessionSpecCommand("s1", spec))
    assert svc.get_spec(GetSessionSpecCommand("s1")) is spec
    assert svc.get_spec(GetSessionSpecCommand("absent")) is None


def test_list_session_ids():
    metrics = _FakeMetrics()
    svc = SessionAdminService(metrics, metrics)  # type: ignore[arg-type]
    svc.set_spec(SetSessionSpecCommand("s2", SessionSpec(client="c", model="m", effort="e")))
    svc.set_spec(SetSessionSpecCommand("s1", SessionSpec(client="c", model="m", effort="e")))
    assert svc.list_session_ids() == ["s1", "s2"]


def test_clear_unknown_session_is_a_noop():
    metrics = _FakeMetrics()
    SessionAdminService(metrics, metrics).clear_spec(ClearSessionSpecCommand("nope"))  # type: ignore[arg-type]
    assert metrics.specs == {}


def test_sessions_for_tag():
    from generic_ml_cache_core.application.port.inbound.session_admin.sessions_for_tag_command import (
        SessionsForTagCommand,
    )

    svc = SessionAdminService(_FakeMetrics(), _FakeMetrics())  # type: ignore[arg-type]
    assert svc.sessions_for_tag(SessionsForTagCommand("t")) == ["s1", "s2"]
    assert svc.sessions_for_tag(SessionsForTagCommand("none")) == []


def test_execution_keys_for_session():
    from generic_ml_cache_core.application.port.inbound.session_admin.execution_keys_for_session_command import (
        ExecutionKeysForSessionCommand,
    )

    svc = SessionAdminService(_FakeMetrics(), _FakeMetrics())  # type: ignore[arg-type]
    assert svc.execution_keys_for_session(ExecutionKeysForSessionCommand("s1")) == ["k1", "k2"]
