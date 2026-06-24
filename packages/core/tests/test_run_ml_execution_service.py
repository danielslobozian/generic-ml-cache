# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunMlExecutionService — the unified managed + API + passthrough executor."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from generic_ml_cache_core.adapter.out.persistence.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.client_runner_port import ClientRunnerPort
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.application.usecase.run_ml_execution_service import RunMlExecutionService
from generic_ml_cache_core.common.errors import CacheMiss


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FakeClientRunner(ClientRunnerPort):
    name = "fake-managed"

    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [ClientRunResult(exit_code=0, stdout="managed out\n")]
        self.calls: List[MlRequest] = []

    def run(self, request: MlRequest) -> ClientRunResult:
        self.calls.append(request)
        if len(self._results) > 1:
            return self._results.pop(0)
        return self._results[0]


class FakeApiClient(ApiClientPort):
    name = "fake-api-runner"

    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [
            ClientRunResult(exit_code=0, stdout="api reply\n", token_usage=TokenUsage(5, 10))
        ]
        self.calls: List[MlRequest] = []

    def run(self, request: MlRequest) -> ClientRunResult:
        self.calls.append(request)
        if len(self._results) > 1:
            return self._results.pop(0)
        return self._results[0]


class FakePassthroughRunner(MlRunnerPort):
    name = "fake-pass"

    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [ClientRunResult(exit_code=0, stdout="native out\n")]
        self.calls: List[MlRequest] = []

    @property
    def execution_kind(self) -> ExecutionKind:
        return ExecutionKind.LOCAL_PASSTHROUGH

    def run(self, request: MlRequest) -> ClientRunResult:
        self.calls.append(request)
        if len(self._results) > 1:
            return self._results.pop(0)
        return self._results[0]


class FakeFileFingerprint(FileFingerprintPort):
    def fingerprint(self, path: str) -> str:
        return "fp_" + path


class FakeBlobStore(BlobStorePort):
    def __init__(self) -> None:
        self.store: Dict[str, bytes] = {}
        self.puts: List[str] = []

    def get(self, key: str) -> Optional[bytes]:
        return self.store.get(key)

    def put(self, key: str, output: bytes) -> None:
        self.store[key] = output
        self.puts.append(key)

    def remove(self, key: str) -> None:
        self.store.pop(key, None)


class FakeMetrics(MetricsPort):
    def __init__(self) -> None:
        self.events: List[dict] = []

    def record_event(self, event, *, execution_key, client, model, effort, session_id=None) -> None:
        self.events.append({"event": event, "client": client, "model": model})

    def hit_counts_by_key(self) -> Dict[str, int]:
        return {}

    def event_counts(self) -> Dict[str, int]:
        return {}

    def session_event_counts(self, session_id) -> Dict[str, int]:
        return {}

    def session_events(self, session_id):
        return []

    def last_access(self) -> Dict[str, float]:
        return {}

    def event_names(self) -> List[str]:
        return [r["event"] for r in self.events]


def _managed_command(**overrides) -> RunMlExecutionCommand:
    base = dict(
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        client="claude",
        model="sonnet",
        effort="",
        context="",
        prompt="hello",
    )
    base.update(overrides)
    return RunMlExecutionCommand(**base)


def _api_command(**overrides) -> RunMlExecutionCommand:
    base = dict(
        execution_kind=ExecutionKind.API,
        client="openai",
        model="gpt-x",
        context="",
        prompt="hi",
    )
    base.update(overrides)
    return RunMlExecutionCommand(**base)


def _passthrough_command(**overrides) -> RunMlExecutionCommand:
    base = dict(
        execution_kind=ExecutionKind.LOCAL_PASSTHROUGH,
        client="claude",
        model="",
        native_args=["--print", "hello"],
    )
    base.update(overrides)
    return RunMlExecutionCommand(**base)


class _Harness:
    def __init__(
        self,
        client_runner: Optional[ClientRunnerPort] = None,
        api_client: Optional[ApiClientPort] = None,
        passthrough_runner: Optional[FakePassthroughRunner] = None,
    ) -> None:
        self.runner = client_runner or FakeClientRunner()
        self.api = api_client or FakeApiClient()
        self.passthrough = passthrough_runner or FakePassthroughRunner()
        self.blob = FakeBlobStore()
        self.repo = InMemoryExecutionRepository(clock=FixedClock())
        self.metrics = FakeMetrics()
        self.service = RunMlExecutionService(
            FakeFileFingerprint(),
            {
                ExecutionKind.LOCAL_MANAGED: self.runner,
                ExecutionKind.API: self.api,
                ExecutionKind.LOCAL_PASSTHROUGH: self.passthrough,
            },
            self.blob,
            self.repo,
            self.metrics,
        )


def _stdout(execution) -> Optional[bytes]:
    for a in execution.artifacts:
        if a.artifact_type is ArtifactType.STDOUT:
            return a.content
    return None


# --- port wiring -------------------------------------------------------------


def test_inbound_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        RunMlExecutionUseCase()  # type: ignore[abstract]


def test_service_implements_the_inbound_port():
    assert isinstance(_Harness().service, RunMlExecutionUseCase)


# --- managed path ------------------------------------------------------------


def test_managed_miss_runs_and_records():
    harness = _Harness(client_runner=FakeClientRunner(ClientRunResult(exit_code=0, stdout="hi\n")))
    execution = harness.service.execute(_managed_command())

    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.execution_kind is ExecutionKind.LOCAL_MANAGED
    assert execution.output_persisted is True
    assert _stdout(execution) == b"hi\n"
    assert len(harness.runner.calls) == 1
    assert harness.api.calls == []
    assert harness.metrics.event_names() == ["record"]


def test_managed_second_call_is_a_cache_hit():
    harness = _Harness(client_runner=FakeClientRunner(ClientRunResult(exit_code=0, stdout="hi\n")))
    harness.service.execute(_managed_command())
    second = harness.service.execute(_managed_command())
    assert len(harness.runner.calls) == 1
    assert _stdout(second) == b"hi\n"
    assert harness.metrics.event_names() == ["record", "hit"]


def test_managed_identity_uses_client_and_inputs():
    harness = _Harness()
    exec_a = harness.service.execute(_managed_command(client="claude", model="m1"))
    exec_b = harness.service.execute(_managed_command(client="codex", model="m1"))
    assert exec_a.call_identity.generate_key() != exec_b.call_identity.generate_key()


def test_managed_journal_records_client():
    harness = _Harness()
    harness.service.execute(_managed_command(client="claude"))
    assert harness.metrics.events[0]["client"] == "claude"


def test_managed_failed_run_not_stored_by_default():
    harness = _Harness(client_runner=FakeClientRunner(ClientRunResult(exit_code=1, stderr="boom")))
    execution = harness.service.execute(_managed_command())
    assert execution.execution_state is ExecutionState.FAILED
    assert execution.output_persisted is False


# --- api path ----------------------------------------------------------------


def test_api_miss_runs_and_records():
    harness = _Harness(
        api_client=FakeApiClient(
            ClientRunResult(exit_code=0, stdout="reply\n", token_usage=TokenUsage(3, 7))
        )
    )
    execution = harness.service.execute(_api_command())

    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.execution_kind is ExecutionKind.API
    assert execution.output_persisted is True
    assert _stdout(execution) == b"reply\n"
    assert execution.token_usage.input_tokens == 3
    assert harness.runner.calls == []
    assert len(harness.api.calls) == 1
    assert harness.metrics.event_names() == ["record"]


def test_api_second_call_is_a_cache_hit():
    harness = _Harness()
    harness.service.execute(_api_command())
    harness.service.execute(_api_command())
    assert len(harness.api.calls) == 1
    assert harness.metrics.event_names() == ["record", "hit"]


def test_api_identity_differs_by_provider_and_prompt():
    harness = _Harness()
    exec_a = harness.service.execute(_api_command(client="openai", prompt="a"))
    exec_b = harness.service.execute(_api_command(client="openai", prompt="b"))
    assert exec_a.call_identity.generate_key() != exec_b.call_identity.generate_key()


def test_api_journal_records_client_as_provider():
    harness = _Harness()
    harness.service.execute(_api_command(client="gemini"))
    assert harness.metrics.events[0]["client"] == "gemini"


# --- managed vs api keys are distinct ----------------------------------------


def test_managed_and_api_keys_never_collide():
    harness = _Harness()
    cmd_m = _managed_command(client="same", model="m", prompt="p")
    cmd_a = _api_command(client="same", model="m", prompt="p")
    managed_key = harness.service.execute(cmd_m).call_identity.generate_key()
    api_key = harness.service.execute(cmd_a).call_identity.generate_key()
    assert managed_key != api_key


# --- IN_PROGRESS lifecycle ---------------------------------------------------


def test_in_progress_recorded_before_final_success():
    harness = _Harness(client_runner=FakeClientRunner(ClientRunResult(exit_code=0, stdout="ok\n")))
    execution = harness.service.execute(_managed_command())
    key = execution.call_identity.generate_key()
    history = harness.repo.find_all(key)
    assert len(history) == 2
    assert history[0].execution_state is ExecutionState.IN_PROGRESS
    assert history[1].execution_state is ExecutionState.SUCCESS


def test_in_progress_recorded_before_final_failure():
    harness = _Harness(client_runner=FakeClientRunner(ClientRunResult(exit_code=1, stderr="err")))
    execution = harness.service.execute(_managed_command())
    key = execution.call_identity.generate_key()
    history = harness.repo.find_all(key)
    assert len(history) == 2
    assert history[0].execution_state is ExecutionState.IN_PROGRESS
    assert history[1].execution_state is ExecutionState.FAILED


def test_uncacheable_run_does_not_record_in_progress():
    harness = _Harness()
    cmd = _managed_command(allow_paths=["/workspace"])
    execution = harness.service.execute(cmd)
    key = execution.call_identity.generate_key()
    assert harness.repo.find_all(key) == []  # no IN_PROGRESS, no final


def test_concurrent_same_key_runs_once(monkeypatch):
    """Two threads with the same key: only one should call the client runner."""
    import threading

    results: list = []
    runner = FakeClientRunner(
        ClientRunResult(exit_code=0, stdout="first\n"),
        ClientRunResult(exit_code=0, stdout="second\n"),
    )
    harness = _Harness(client_runner=runner)

    def _run():
        results.append(harness.service.execute(_managed_command()))

    t1 = threading.Thread(target=_run)
    t2 = threading.Thread(target=_run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(runner.calls) == 1  # only one real client call
    assert len(results) == 2  # both callers got a result
    assert all(r.execution_state is ExecutionState.SUCCESS for r in results)


# --- cache modes (shared behaviour) ------------------------------------------


def test_offline_miss_raises():
    harness = _Harness()
    with pytest.raises(CacheMiss):
        harness.service.execute(_managed_command(cache_mode=CacheMode.OFFLINE))
    assert harness.runner.calls == []


def test_refresh_bypasses_cache():
    harness = _Harness(
        client_runner=FakeClientRunner(
            ClientRunResult(exit_code=0, stdout="old\n"),
            ClientRunResult(exit_code=0, stdout="new\n"),
        )
    )
    harness.service.execute(_managed_command())
    harness.service.execute(_managed_command(cache_mode=CacheMode.REFRESH))
    assert len(harness.runner.calls) == 2


# --- passthrough path --------------------------------------------------------


def test_passthrough_records_result_with_local_passthrough_kind():
    harness = _Harness(
        passthrough_runner=FakePassthroughRunner(
            ClientRunResult(exit_code=0, stdout="native out\n")
        )
    )
    execution = harness.service.execute(_passthrough_command())

    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH
    assert execution.output_persisted is True
    assert _stdout(execution) == b"native out\n"
    assert len(harness.passthrough.calls) == 1
    assert harness.runner.calls == []
    assert harness.api.calls == []
    assert harness.metrics.event_names() == ["record"]


def test_passthrough_cache_hit_replays():
    harness = _Harness(
        passthrough_runner=FakePassthroughRunner(
            ClientRunResult(exit_code=0, stdout="native out\n")
        )
    )
    harness.service.execute(_passthrough_command())
    second = harness.service.execute(_passthrough_command())
    assert len(harness.passthrough.calls) == 1
    assert _stdout(second) == b"native out\n"
    assert harness.metrics.event_names() == ["record", "hit"]


def test_passthrough_is_tagged_local_passthrough():
    harness = _Harness()
    execution = harness.service.execute(_passthrough_command())
    assert execution.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH


def test_passthrough_native_args_in_identity():
    harness = _Harness()
    exec_a = harness.service.execute(_passthrough_command(native_args=["--help"]))
    exec_b = harness.service.execute(_passthrough_command(native_args=["--version"]))
    assert exec_a.call_identity.generate_key() != exec_b.call_identity.generate_key()
