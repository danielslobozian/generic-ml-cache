# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunPassthroughExecutionService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from generic_ml_cache_core.adapter.out.persistence.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.port.inbound.run_passthrough_execution_command import (
    RunPassthroughExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_passthrough_execution_use_case import (
    RunPassthroughExecutionUseCase,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.port.out.passthrough_runner_port import PassthroughRunnerPort
from generic_ml_cache_core.application.usecase.run_passthrough_execution_service import (
    RunPassthroughExecutionService,
)
from generic_ml_cache_core.common.errors import CacheMiss


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FakePassthroughRunner(PassthroughRunnerPort):
    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [ClientRunResult(exit_code=0, stdout="native out\n")]
        self.calls: List[tuple] = []

    def run(self, client: str, native_args: List[str]) -> ClientRunResult:
        self.calls.append((client, list(native_args)))
        if len(self._results) > 1:
            return self._results.pop(0)
        return self._results[0]


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

    def record_event(self, event, *, execution_key, client, model, effort) -> None:
        self.events.append({"event": event, "client": client, "model": model, "effort": effort})

    def hit_counts_by_key(self) -> Dict[str, int]:
        return {}

    def event_counts(self) -> Dict[str, int]:
        return {}

    def last_access(self) -> Dict[str, float]:
        return {}

    def event_names(self) -> List[str]:
        return [recorded["event"] for recorded in self.events]


def _command(**overrides) -> RunPassthroughExecutionCommand:
    base = dict(client="claude", native_args=["--print", "hello"])
    base.update(overrides)
    return RunPassthroughExecutionCommand(**base)


class _Harness:
    def __init__(self, *results: ClientRunResult) -> None:
        self.runner = FakePassthroughRunner(*results)
        self.blob = FakeBlobStore()
        self.repository = InMemoryExecutionRepository(clock=FixedClock())
        self.metrics = FakeMetrics()
        self.service = RunPassthroughExecutionService(
            self.runner, self.blob, self.repository, self.metrics
        )


def _stdout(execution) -> Optional[bytes]:
    for artifact in execution.artifacts:
        if artifact.artifact_type is ArtifactType.STDOUT:
            return artifact.content
    return None


# --- port wiring -------------------------------------------------------------


def test_inbound_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        RunPassthroughExecutionUseCase()  # type: ignore[abstract]


def test_service_implements_the_inbound_port():
    assert isinstance(_Harness().service, RunPassthroughExecutionUseCase)


# --- miss / record -----------------------------------------------------------


def test_miss_runs_records_and_returns_a_passthrough_success():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    execution = harness.service.execute(_command())

    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH
    assert execution.output_persisted is True
    assert _stdout(execution) == b"answer\n"
    assert harness.runner.calls == [("claude", ["--print", "hello"])]
    assert harness.metrics.event_names() == ["record"]


def test_passthrough_captures_no_files():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="out", stderr="err"))
    execution = harness.service.execute(_command())
    types = [artifact.artifact_type for artifact in execution.artifacts]
    assert ArtifactType.OUTPUT_FILE not in types
    assert ArtifactType.STDOUT in types and ArtifactType.STDERR in types


def test_journal_records_client_with_empty_model_and_effort():
    harness = _Harness()
    harness.service.execute(_command())
    recorded = harness.metrics.events[0]
    assert recorded["client"] == "claude"
    assert recorded["model"] == ""
    assert recorded["effort"] == ""


# --- hit / replay ------------------------------------------------------------


def test_second_identical_call_is_served_from_cache():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    harness.service.execute(_command())
    second = harness.service.execute(_command())
    assert len(harness.runner.calls) == 1
    assert harness.metrics.event_names() == ["record", "hit"]
    assert _stdout(second) == b"answer\n"


def test_different_native_args_miss_and_run_again():
    harness = _Harness()
    harness.service.execute(_command(native_args=["a"]))
    harness.service.execute(_command(native_args=["b"]))
    assert len(harness.runner.calls) == 2


# --- modes -------------------------------------------------------------------


def test_refresh_always_runs_and_supersedes():
    harness = _Harness(
        ClientRunResult(exit_code=0, stdout="old\n"),
        ClientRunResult(exit_code=0, stdout="new\n"),
    )
    first = harness.service.execute(_command())
    harness.service.execute(_command(cache_mode=CacheMode.REFRESH))
    key = first.call_identity.generate_key()
    assert len(harness.runner.calls) == 2
    assert len(harness.repository.find_all(key)) == 2
    assert _stdout(harness.service.execute(_command())) == b"new\n"


def test_offline_miss_raises_and_does_not_run():
    harness = _Harness()
    with pytest.raises(CacheMiss):
        harness.service.execute(_command(cache_mode=CacheMode.OFFLINE))
    assert harness.runner.calls == []
    assert harness.metrics.event_names() == ["miss"]


def test_offline_hit_serves_from_cache():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    harness.service.execute(_command())
    served = harness.service.execute(_command(cache_mode=CacheMode.OFFLINE))
    assert len(harness.runner.calls) == 1
    assert _stdout(served) == b"answer\n"


# --- failure / persistence ---------------------------------------------------


def test_failed_call_is_not_stored_by_default():
    harness = _Harness(ClientRunResult(exit_code=2, stderr="boom\n"))
    execution = harness.service.execute(_command())
    key = execution.call_identity.generate_key()
    assert execution.execution_state is ExecutionState.FAILED
    assert execution.output_persisted is False
    assert execution.failure.exit_code == 2
    assert harness.repository.find_current(key) is None
    assert harness.metrics.event_names() == ["run"]


def test_failed_call_stored_with_record_on_error():
    harness = _Harness(ClientRunResult(exit_code=2, stderr="boom\n"))
    execution = harness.service.execute(_command(record_on_error=True))
    assert execution.output_persisted is True
    assert harness.metrics.event_names() == ["record"]


def test_persist_output_false_stores_nothing():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="secret\n"))
    execution = harness.service.execute(_command(persist_output=False))
    key = execution.call_identity.generate_key()
    assert execution.output_persisted is False
    assert _stdout(execution) == b"secret\n"
    assert harness.repository.find_current(key) is None
    assert harness.blob.puts == []
    assert harness.metrics.event_names() == ["run"]
