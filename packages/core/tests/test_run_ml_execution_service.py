# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunMlExecutionService — the unified managed + API + passthrough executor."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.run.workspace import Snapshot, Workspace
from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.inbound.purge.evict_to_quota_command import (
    EvictToQuotaCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.outbound.api_client_port import ApiClientPort
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.call_journal_ports import (
    CallStatsPort,
    PurgeJournalPort,
    RecordCallEventPort,
    SessionQueryPort,
    SessionReportSourcePort,
    SessionSpecPort,
    SessionTagsPort,
)
from generic_ml_cache_core.application.port.outbound.clock_port import ClockPort
from generic_ml_cache_core.application.port.outbound.file_fingerprint_port import (
    FileFingerprintPort,
)
from generic_ml_cache_core.application.port.outbound.local_client_port import LocalClientPort
from generic_ml_cache_core.application.port.outbound.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.application.port.outbound.passthrough_local_runner_port import (
    PassthroughLocalRunnerPort,
)
from generic_ml_cache_core.application.port.outbound.workspace_port import WorkspacePort
from generic_ml_cache_core.application.usecase.run_ml_execution_service import RunMlExecutionService
from generic_ml_cache_core.common.errors import (
    CacheMiss,
    RunInterrupted,
    UnknownClient,
    UnsupportedExecutionMode,
)
from generic_ml_cache_core.testing.in_memory_execution_repository import (
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

    def capture(self, run_dir, baseline) -> list:
        return []

    def dispose(self, workspace) -> None:
        pass


class FakeClientRunner:
    name = "fake-managed"
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [ClientRunResult(exit_code=0, stdout="managed out\n")]
        self.calls: list = []

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
        self.calls: list[MlRequest] = []

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
        self.calls: list = []

    def execute_passthrough(self, request) -> ClientAnswer:
        self.calls.append(request)
        result = self._results.pop(0) if len(self._results) > 1 else self._results[0]
        return _as_answer(result)


class FakeFileFingerprint(FileFingerprintPort):
    def fingerprint(self, path: str) -> str:
        return "fp_" + path


class FakeBlobStore(BlobStorePort):
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.puts: list[str] = []

    def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    def put(self, key: str, output: bytes) -> None:
        self.store[key] = output
        self.puts.append(key)

    def exists(self, key: str) -> bool:
        return key in self.store

    def is_healthy(self) -> bool:
        return True

    def remove(self, key: str) -> None:
        self.store.pop(key, None)


class FakeMetrics(
    RecordCallEventPort,
    CallStatsPort,
    SessionReportSourcePort,
    SessionQueryPort,
    PurgeJournalPort,
    SessionTagsPort,
    SessionSpecPort,
):
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record_event(self, event, *, execution_key, client, model, effort, session_id=None) -> None:
        self.events.append({"event": event, "client": client, "model": model})

    def hit_counts_by_key(self) -> dict[str, int]:
        return {}

    def event_counts(self) -> dict[str, int]:
        return {}

    def session_event_counts(self, session_id) -> dict[str, int]:
        return {}

    def session_events(self, session_id):
        return []

    def last_access(self) -> dict[str, float]:
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

    def session_spec(self, session_id) -> SessionSpec | None:
        return None

    def list_session_ids(self) -> list[str]:
        return []

    def session_tags(self, session_id) -> list[str]:
        return []

    def session_ids_for_tag(self, tag) -> list[str]:
        return []

    def event_names(self) -> list[str]:
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


class _DispatchRunner(LocalClientPort, MlRunnerPort):
    """One fake that answers every execution kind by delegating to the kind-specific
    fake — so the harness can wire a single client name to all three. It really
    implements both driven-client ports (a real adapter answers only its own kind;
    this is a test convenience so the existing per-kind fakes and their assertions
    stay unchanged), which also satisfies the W18 capability check before dispatch."""

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

    # -- LocalClientPort probe/listing surface (unused by these tests) --------
    def resolve_executable(self, override: str | None) -> str:
        return override or "fake"

    def version_argv(self, executable: str) -> list[str]:
        return [executable, "--version"]

    def models_argv(self, executable: str) -> list[str] | None:
        return None

    def parse_model_list(self, stdout: str) -> list[ModelInfo]:
        return []


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
        client_runner: FakeClientRunner | None = None,
        api_client: ApiClientPort | None = None,
        passthrough_runner: FakePassthroughRunner | None = None,
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
            save=self.repo,
            read=self.repo,
            annotate=self.repo,
            record=self.metrics,
            workspace=FakeWorkspace(),
        )


def _stdout(execution) -> bytes | None:
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


def test_recorded_run_marks_artifacts_stored():
    harness = _Harness(client_runner=FakeClientRunner(ClientRunResult(exit_code=0, stdout="hi\n")))
    execution = harness.service.execute(_managed_command())
    assert execution.output_persisted is True
    assert execution.artifacts  # stdout + stderr
    assert all(a.status is ArtifactStatus.STORED for a in execution.artifacts)


def test_blob_write_failure_is_intercepted_and_surfaced():
    # DB-first + C-4: a failing blob write must NOT throw out of execute(); it marks
    # the artifacts FAILED with a detail, leaves the run non-servable (not cached),
    # and does not orphan a blob.
    harness = _Harness(client_runner=FakeClientRunner(ClientRunResult(exit_code=0, stdout="hi\n")))

    class _FailingBlobStore(FakeBlobStore):
        def put(self, key: str, output: bytes) -> None:
            raise OSError("disk full")

    harness.blob = _FailingBlobStore()
    harness.service = RunMlExecutionService(
        FakeFileFingerprint(),
        _runners_for(harness.runner, harness.passthrough, harness.api),
        harness.blob,
        save=harness.repo,
        read=harness.repo,
        annotate=harness.repo,
        record=harness.metrics,
        workspace=FakeWorkspace(),
    )

    execution = harness.service.execute(_managed_command())  # must not raise

    key = execution.call_identity.generate_key()
    assert execution.output_persisted is False
    assert execution.artifacts
    assert all(a.status is ArtifactStatus.FAILED for a in execution.artifacts)
    assert all(a.status_detail for a in execution.artifacts)
    # Not servable: a failed-to-store run is not cached.
    assert harness.repo.find_current(key) is None
    # No blob was orphaned (the put failed, so nothing landed).
    assert harness.blob.store == {}
    # A subsequent call re-runs the client (the store never became servable).
    harness.service.execute(_managed_command())
    assert len(harness.runner.calls) == 2


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


def test_in_progress_row_is_visible_while_the_client_runs_then_updated_in_place():
    # W1: one row per run. It is saved IN_PROGRESS before the client is called (so
    # an external observer sees the in-flight run), then transitioned in place to
    # SUCCESS — never a second insert whose "latest by key" a racer could steal.
    seen_during_run: list[list[ExecutionState]] = []

    class _PeekingRunner(FakeClientRunner):
        def execute_managed(self, request, workspace):
            seen_during_run.append(
                [
                    execution.execution_state
                    for key in harness.repo.all_execution_keys()
                    for execution in harness.repo.find_all(key)
                ]
            )
            return super().execute_managed(request, workspace)

    harness = _Harness(client_runner=_PeekingRunner(ClientRunResult(exit_code=0, stdout="ok\n")))
    execution = harness.service.execute(_managed_command())
    key = execution.call_identity.generate_key()

    assert seen_during_run == [[ExecutionState.IN_PROGRESS]]
    history = harness.repo.find_all(key)
    assert len(history) == 1
    assert history[0].execution_state is ExecutionState.SUCCESS


def test_in_progress_row_transitions_to_failure_in_place():
    harness = _Harness(client_runner=FakeClientRunner(ClientRunResult(exit_code=1, stderr="err")))
    execution = harness.service.execute(_managed_command())
    key = execution.call_identity.generate_key()
    history = harness.repo.find_all(key)
    assert len(history) == 1  # one row, updated in place (no orphan IN_PROGRESS — W2)
    assert history[0].execution_state is ExecutionState.FAILED


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
        self.evict_calls: list[int] = []

    def evict_to_quota(self, command: EvictToQuotaCommand) -> PurgeReport:
        self.evict_calls.append(command.max_bytes)
        return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)

    # PurgeService has other methods the hook doesn't call — not needed here.


def _harness_with_quota(max_size: int | None) -> tuple:
    harness = _Harness()
    spy = _SpyPurge()
    service = RunMlExecutionService(
        FakeFileFingerprint(),
        _runners_for(harness.runner, harness.passthrough, harness.api),
        harness.blob,
        save=harness.repo,
        read=harness.repo,
        annotate=harness.repo,
        record=harness.metrics,
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
        save=failing_harness.repo,
        read=failing_harness.repo,
        annotate=failing_harness.repo,
        record=failing_harness.metrics,
        purge_service=spy,
        max_size=1_000_000,
        workspace=FakeWorkspace(),
    )
    failing_service.execute(_managed_command())
    assert spy.evict_calls == []


# --- W18: structured dispatch errors -----------------------------------------


def _service_with_runners(runners) -> RunMlExecutionService:
    repo = InMemoryExecutionRepository(clock=FixedClock())
    return RunMlExecutionService(
        FakeFileFingerprint(),
        runners,
        FakeBlobStore(),
        save=repo,
        read=repo,
        annotate=repo,
        record=FakeMetrics(),
        workspace=FakeWorkspace(),
    )


def test_unknown_client_raises_unknown_client_not_runtime_error():
    # No runner registered for the requested client — the core fallback raises a
    # named UnknownClient (drivers map it), never a raw RuntimeError (W18).
    service = _service_with_runners({})
    with pytest.raises(UnknownClient):
        service.execute(_managed_command(client="mistral"))


def test_wrong_kind_runner_raises_unsupported_execution_mode():
    # An API-only adapter (an MlRunnerPort, not a LocalClientPort) is registered but
    # asked to run a managed local command. The capability is checked before the
    # cast, so it raises UnsupportedExecutionMode, not an AttributeError (W18).
    service = _service_with_runners({"claude": FakeApiClient()})
    with pytest.raises(UnsupportedExecutionMode):
        service.execute(_managed_command(client="claude"))


# --- S3c-ii: clean up the in-progress row when the client raises -------------


class _RaisingRunner(FakeClientRunner):
    def __init__(self, exc: BaseException) -> None:
        super().__init__()
        self._exc = exc

    def execute_managed(self, request, workspace) -> ClientAnswer:
        raise self._exc


def test_client_raise_marks_the_in_progress_row_failed_not_dangling():
    harness = _Harness(client_runner=_RaisingRunner(ValueError("provider died")))
    with pytest.raises(ValueError):
        harness.service.execute(_managed_command())
    keys = harness.repo.all_execution_keys()
    assert len(keys) == 1
    history = harness.repo.find_all(keys[0])
    assert len(history) == 1  # one row, transitioned in place — no dangling IN_PROGRESS
    assert history[0].execution_state is ExecutionState.FAILED


def test_run_interrupted_removes_the_in_progress_row_entirely():
    harness = _Harness(client_runner=_RaisingRunner(RunInterrupted("stopped by signal")))
    with pytest.raises(RunInterrupted):
        harness.service.execute(_managed_command())
    # A requested stop is never recorded — the row is gone.
    assert harness.repo.all_execution_keys() == []


# --- W17/S4: corrupt-cassette self-heal --------------------------------------


def test_missing_output_blob_on_hit_self_heals_by_rerunning():
    runner = FakeClientRunner(
        ClientRunResult(exit_code=0, stdout="v1\n"),
        ClientRunResult(exit_code=0, stdout="v2\n"),
    )
    harness = _Harness(client_runner=runner)
    first = harness.service.execute(_managed_command())
    assert _stdout(first) == b"v1\n"

    # Corrupt the cassette: its output blob vanishes from the store.
    harness.blob.store.clear()

    second = harness.service.execute(_managed_command())
    # A would-be hit we cannot hydrate becomes a miss → re-run, replacing it.
    assert _stdout(second) == b"v2\n"
    assert len(harness.runner.calls) == 2  # ran again to self-heal


def test_missing_output_blob_offline_degrades_to_a_clean_miss():
    harness = _Harness()
    harness.service.execute(_managed_command())
    harness.blob.store.clear()  # corrupt the cassette
    # OFFLINE cannot re-run, so it is a clean CacheMiss, not a crash or partial serve.
    with pytest.raises(CacheMiss):
        harness.service.execute(_managed_command(cache_mode=CacheMode.OFFLINE))


# --- W24: role-port split of LocalClientPort ---------------------------------


def test_a_runner_implementing_only_the_passthrough_role_cannot_run_managed():
    # W24 ISP: a runner that implements only PassthroughLocalRunnerPort (not the
    # managed role) is rejected for a managed command with a named error — the
    # capability check narrows to the exact role port the mode needs.
    class _PassthroughOnly(PassthroughLocalRunnerPort):
        name = "pass-only"
        execution_kind = ExecutionKind.LOCAL_PASSTHROUGH

        def resolve_executable(self, override):
            return override or "x"

        def execute_passthrough(self, request):
            return _as_answer(ClientRunResult(exit_code=0, stdout="native\n"))

    service = _service_with_runners({"pass-only": _PassthroughOnly()})
    with pytest.raises(UnsupportedExecutionMode):
        service.execute(_managed_command(client="pass-only"))
