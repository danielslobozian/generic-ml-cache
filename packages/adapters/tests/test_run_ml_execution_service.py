# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunMlExecutionService — the unified managed + API + passthrough executor."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pytest
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.run.workspace import Snapshot, Workspace
from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.port.out.workspace_port import WorkspacePort
from generic_ml_cache_core.application.usecase.run_ml_execution_service import RunMlExecutionService
from generic_ml_cache_core.common.errors import CacheMiss

from generic_ml_cache_adapters.adapter.out.persistence.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


def _as_answer(result: ClientRunResult) -> ClientAnswer:
    return ClientAnswer(
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        token_usage=result.token_usage,
    )


class FakeWorkspace(WorkspacePort):
    """A no-op workspace: the managed use case drives it, but these tests assert on
    stdout/exit/cache behavior, not captured artifacts, so capture returns nothing."""

    def create(self) -> Workspace:
        return Workspace(run_dir=Path("/run"), config_home=Path("/home"))

    def write_config(self, workspace, config_file) -> None:
        pass

    def seed_credentials(self, workspace, credentials) -> None:
        pass

    def snapshot(self, run_dir) -> Snapshot:
        return Snapshot()

    def capture(self, run_dir, baseline) -> List:
        return []

    def dispose(self, workspace) -> None:
        pass


class FakeClientRunner:
    name = "fake-managed"
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [ClientRunResult(exit_code=0, stdout="managed out\n")]
        self.calls: List = []

    def stage_inputs(self, request, workspace) -> None:
        pass

    def execute_managed(self, request, workspace) -> ClientAnswer:
        self.calls.append(request)
        result = self._results.pop(0) if len(self._results) > 1 else self._results[0]
        return _as_answer(result)


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


class FakePassthroughRunner:
    name = "fake-pass"
    execution_kind = ExecutionKind.LOCAL_PASSTHROUGH

    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [ClientRunResult(exit_code=0, stdout="native out\n")]
        self.calls: List = []

    def execute_passthrough(self, request) -> ClientAnswer:
        self.calls.append(request)
        result = self._results.pop(0) if len(self._results) > 1 else self._results[0]
        return _as_answer(result)


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

    def execution_keys_for_session(self, session_id):
        return []

    def delete_events_for_key(self, execution_key) -> None:
        pass

    def add_session_tag(self, session_id, tag) -> None:
        pass

    def remove_session_tag(self, session_id, tag) -> None:
        pass

    def set_session_spec(self, session_id, spec: SessionSpec) -> None:
        pass

    def clear_session_spec(self, session_id) -> None:
        pass

    def session_spec(self, session_id) -> Optional[SessionSpec]:
        return None

    def list_session_ids(self) -> List[str]:
        return []

    def session_tags(self, session_id) -> List[str]:
        return []

    def session_ids_for_tag(self, tag) -> List[str]:
        return []

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


class _DispatchRunner:
    """One fake that answers every execution kind by delegating to the kind-specific
    fake — so the harness can wire a single client name to all three. (A real client
    name has one boundary, so it answers only its own kinds; this is a test convenience
    that lets the existing per-kind fakes and their assertions stay unchanged.)"""

    name = "fake"
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(self, managed, passthrough, api) -> None:
        self._managed = managed
        self._passthrough = passthrough
        self._api = api

    def stage_inputs(self, request, workspace) -> None:
        self._managed.stage_inputs(request, workspace)

    def execute_managed(self, request, workspace) -> ClientAnswer:
        return self._managed.execute_managed(request, workspace)

    def execute_passthrough(self, request) -> ClientAnswer:
        return self._passthrough.execute_passthrough(request)

    def run(self, request: MlRequest) -> ClientRunResult:
        return self._api.run(request)


class _AnyClientRunners(dict):
    """A name->runner map that answers *every* client name with one dispatcher, so a
    test need not enumerate client names. The real service receives an explicit map
    with one entry per client it serves; tests just route everything to their fakes."""

    def __init__(self, dispatcher: _DispatchRunner) -> None:
        super().__init__()
        self._dispatcher = dispatcher

    def get(self, key, default=None):  # noqa: ARG002
        return self._dispatcher


def _runners_for(managed, passthrough, api) -> _AnyClientRunners:
    return _AnyClientRunners(_DispatchRunner(managed, passthrough, api))


class _Harness:
    def __init__(
        self,
        client_runner: Optional[FakeClientRunner] = None,
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
            _runners_for(self.runner, self.passthrough, self.api),
            self.blob,
            self.repo,
            self.metrics,
            workspace=FakeWorkspace(),
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


# --- LRU auto-eviction hook --------------------------------------------------


class _SpyPurge:
    """Minimal stub that records every evict_to_quota call."""

    def __init__(self) -> None:
        self.evict_calls: List[int] = []

    def evict_to_quota(self, max_bytes: int) -> PurgeReport:
        self.evict_calls.append(max_bytes)
        return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)

    # PurgeService has other methods the hook doesn't call — not needed here.


def _harness_with_quota(max_size: Optional[int]) -> tuple:
    harness = _Harness()
    spy = _SpyPurge()
    service = RunMlExecutionService(
        FakeFileFingerprint(),
        _runners_for(harness.runner, harness.passthrough, harness.api),
        harness.blob,
        harness.repo,
        harness.metrics,
        purge_service=spy,
        max_size=max_size,
        workspace=FakeWorkspace(),
    )
    return service, spy


def test_eviction_triggered_after_successful_record():
    service, spy = _harness_with_quota(max_size=1_000_000)
    service.execute(_managed_command())
    assert len(spy.evict_calls) == 1
    assert spy.evict_calls[0] == 1_000_000


def test_eviction_not_triggered_when_max_size_is_none():
    service, spy = _harness_with_quota(max_size=None)
    service.execute(_managed_command())
    assert spy.evict_calls == []


def test_eviction_not_triggered_on_cache_hit():
    service, spy = _harness_with_quota(max_size=1_000_000)
    service.execute(_managed_command())  # first run — record
    assert len(spy.evict_calls) == 1
    service.execute(_managed_command())  # second run — cache hit
    assert len(spy.evict_calls) == 1  # eviction not called again


def test_eviction_not_triggered_on_failed_run():
    from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult

    service, spy = _harness_with_quota(max_size=1_000_000)
    failing_harness = _Harness(
        client_runner=FakeClientRunner(ClientRunResult(exit_code=1, stdout="", stderr="boom"))
    )
    failing_service = RunMlExecutionService(
        FakeFileFingerprint(),
        _runners_for(failing_harness.runner, failing_harness.passthrough, failing_harness.api),
        failing_harness.blob,
        failing_harness.repo,
        failing_harness.metrics,
        purge_service=spy,
        max_size=1_000_000,
        workspace=FakeWorkspace(),
    )
    failing_service.execute(_managed_command())
    assert spy.evict_calls == []
