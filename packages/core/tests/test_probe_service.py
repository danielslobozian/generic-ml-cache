# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from unittest.mock import create_autospec

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.gateway_call_identity import (
    GatewayCallIdentity,
)
from generic_ml_cache_core.application.domain.model.probe.probe_status import ProbeStatus
from generic_ml_cache_core.application.port.inbound.probe.probe_command import ProbeCommand
from generic_ml_cache_core.application.port.outbound.file_fingerprint_port import (
    FileFingerprintPort,
)
from generic_ml_cache_core.application.port.outbound.ml_run_ports import ReadMlRunPort
from generic_ml_cache_core.application.usecase.probe_service import ProbeService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cmd(
    uncacheable: bool = False,
    model: str = "m1",
    prompt: str = "hello",
) -> ProbeCommand:
    return ProbeCommand(
        client="claude",
        model=model,
        effort="low",
        context="ctx",
        prompt=prompt,
        allow_paths=["some/path"] if uncacheable else [],
        scan_trust=False,
    )


def _make_stored_execution() -> MlExecution:
    return MlExecution(
        call_identity=GatewayCallIdentity(cache_key="stored-key"),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
    )


def _make_svc(fp=None, repo=None):
    return ProbeService(
        file_fingerprint=fp or create_autospec(FileFingerprintPort),
        repository=repo or create_autospec(ReadMlRunPort),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProbeUncacheable:
    def test_returns_non_cacheable_status(self):
        repo = create_autospec(ReadMlRunPort)
        svc = _make_svc(repo=repo)

        report = svc.execute(_make_cmd(uncacheable=True))

        assert report.status == ProbeStatus.NON_CACHEABLE

    def test_does_not_query_repository(self):
        repo = create_autospec(ReadMlRunPort)
        svc = _make_svc(repo=repo)

        svc.execute(_make_cmd(uncacheable=True))

        repo.find_current.assert_not_called()

    def test_execution_key_is_present_in_report(self):
        svc = _make_svc()

        report = svc.execute(_make_cmd(uncacheable=True))

        assert report.execution_key
        assert len(report.execution_key) > 0

    def test_execution_is_none_in_report(self):
        svc = _make_svc()

        report = svc.execute(_make_cmd(uncacheable=True))

        assert report.execution is None


class TestProbeMiss:
    def test_returns_miss_status_when_find_current_returns_none(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        report = svc.execute(_make_cmd())

        assert report.status == ProbeStatus.MISS

    def test_execution_is_none_on_miss(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        report = svc.execute(_make_cmd())

        assert report.execution is None

    def test_execution_key_is_non_empty_on_miss(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        report = svc.execute(_make_cmd())

        assert report.execution_key and len(report.execution_key) > 0

    def test_find_current_called_with_derived_key(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)
        cmd = _make_cmd()

        report = svc.execute(cmd)

        repo.find_current.assert_called_once_with(report.execution_key)


class TestProbeHit:
    def test_returns_hit_status_when_find_current_returns_execution(self):
        stored = _make_stored_execution()
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = stored
        svc = _make_svc(repo=repo)

        report = svc.execute(_make_cmd())

        assert report.status == ProbeStatus.HIT

    def test_execution_field_is_the_stored_execution(self):
        stored = _make_stored_execution()
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = stored
        svc = _make_svc(repo=repo)

        report = svc.execute(_make_cmd())

        assert report.execution is stored

    def test_execution_key_is_non_empty_on_hit(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = _make_stored_execution()
        svc = _make_svc(repo=repo)

        report = svc.execute(_make_cmd())

        assert report.execution_key and len(report.execution_key) > 0


class TestProbeKey:
    def test_same_command_produces_same_key(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        r1 = svc.execute(_make_cmd(model="m1"))
        r2 = svc.execute(_make_cmd(model="m1"))

        assert r1.execution_key == r2.execution_key

    def test_different_model_produces_different_key(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        r1 = svc.execute(_make_cmd(model="m1"))
        r2 = svc.execute(_make_cmd(model="m2"))

        assert r1.execution_key != r2.execution_key

    def test_different_prompt_produces_different_key(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        r1 = svc.execute(_make_cmd(prompt="ask A"))
        r2 = svc.execute(_make_cmd(prompt="ask B"))

        assert r1.execution_key != r2.execution_key

    def test_cacheable_and_uncacheable_same_fields_different_status_but_consistent_key(self):
        repo = create_autospec(ReadMlRunPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        cacheable = svc.execute(_make_cmd(uncacheable=False))
        repo.find_current.return_value = None  # reset for second call

        assert cacheable.status == ProbeStatus.MISS
        assert cacheable.execution_key
