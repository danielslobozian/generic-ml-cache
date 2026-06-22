# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunApiExecutionService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from generic_ml_cache_core.adapter.out.api.stub_api_client_adapter import StubApiClientAdapter
from generic_ml_cache_core.adapter.out.persistence.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.run.message import Message
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.inbound.run_api_execution_command import (
    RunApiExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_api_execution_use_case import (
    RunApiExecutionUseCase,
)
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.usecase.run_api_execution_service import (
    RunApiExecutionService,
)
from generic_ml_cache_core.common.errors import CacheMiss


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FakeApiClient(ApiClientPort):
    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [ClientRunResult(exit_code=0, stdout="reply\n")]
        self.calls: List[tuple] = []

    def run(self, provider: str, model: str, messages: List[Message]) -> ClientRunResult:
        self.calls.append((provider, model, list(messages)))
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


def _command(**overrides) -> RunApiExecutionCommand:
    base = dict(provider="openai", model="gpt-x", messages=[Message(role="user", content="hi")])
    base.update(overrides)
    return RunApiExecutionCommand(**base)


class _Harness:
    def __init__(self, api_client: Optional[ApiClientPort] = None) -> None:
        self.api_client = api_client or FakeApiClient()
        self.blob = FakeBlobStore()
        self.repository = InMemoryExecutionRepository(clock=FixedClock())
        self.metrics = FakeMetrics()
        self.service = RunApiExecutionService(
            self.api_client, self.blob, self.repository, self.metrics
        )


def _stdout(execution) -> Optional[bytes]:
    for artifact in execution.artifacts:
        if artifact.artifact_type is ArtifactType.STDOUT:
            return artifact.content
    return None


# --- port wiring -------------------------------------------------------------


def test_inbound_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        RunApiExecutionUseCase()  # type: ignore[abstract]


def test_service_implements_the_inbound_port():
    assert isinstance(_Harness().service, RunApiExecutionUseCase)


# --- miss / record -----------------------------------------------------------


def test_miss_runs_records_and_returns_an_api_success():
    harness = _Harness(
        FakeApiClient(
            ClientRunResult(exit_code=0, stdout="answer\n", token_usage=TokenUsage(input_tokens=5))
        )
    )
    execution = harness.service.execute(_command())
    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.execution_kind is ExecutionKind.API
    assert execution.output_persisted is True
    assert _stdout(execution) == b"answer\n"
    assert execution.token_usage.input_tokens == 5  # usage flows onto the execution
    assert harness.metrics.event_names() == ["record"]


def test_api_captures_no_files():
    harness = _Harness(FakeApiClient(ClientRunResult(exit_code=0, stdout="reply")))
    execution = harness.service.execute(_command())
    types = [artifact.artifact_type for artifact in execution.artifacts]
    assert ArtifactType.OUTPUT_FILE not in types


def test_journal_records_provider_and_model():
    harness = _Harness()
    harness.service.execute(_command())
    recorded = harness.metrics.events[0]
    assert recorded["client"] == "openai"
    assert recorded["model"] == "gpt-x"
    assert recorded["effort"] == ""


# --- hit / replay ------------------------------------------------------------


def test_second_identical_call_is_served_from_cache():
    harness = _Harness(FakeApiClient(ClientRunResult(exit_code=0, stdout="answer\n")))
    harness.service.execute(_command())
    second = harness.service.execute(_command())
    assert len(harness.api_client.calls) == 1
    assert harness.metrics.event_names() == ["record", "hit"]
    assert _stdout(second) == b"answer\n"


def test_different_messages_miss_and_run_again():
    harness = _Harness()
    harness.service.execute(_command(messages=[Message(role="user", content="a")]))
    harness.service.execute(_command(messages=[Message(role="user", content="b")]))
    assert len(harness.api_client.calls) == 2


# --- modes -------------------------------------------------------------------


def test_refresh_always_runs_and_supersedes():
    harness = _Harness(
        FakeApiClient(
            ClientRunResult(exit_code=0, stdout="old\n"),
            ClientRunResult(exit_code=0, stdout="new\n"),
        )
    )
    first = harness.service.execute(_command())
    harness.service.execute(_command(cache_mode=CacheMode.REFRESH))
    key = first.call_identity.generate_key()
    assert len(harness.api_client.calls) == 2
    assert len(harness.repository.find_all(key)) == 2


def test_offline_miss_raises_and_does_not_call():
    harness = _Harness()
    with pytest.raises(CacheMiss):
        harness.service.execute(_command(cache_mode=CacheMode.OFFLINE))
    assert harness.api_client.calls == []


# --- failure / persistence ---------------------------------------------------


def test_failed_call_is_not_stored_by_default():
    harness = _Harness(FakeApiClient(ClientRunResult(exit_code=1, stderr="rate limited\n")))
    execution = harness.service.execute(_command())
    key = execution.call_identity.generate_key()
    assert execution.execution_state is ExecutionState.FAILED
    assert execution.output_persisted is False
    assert harness.repository.find_current(key) is None
    assert harness.metrics.event_names() == ["run"]


def test_meter_depth_stores_nothing():
    harness = _Harness(FakeApiClient(ClientRunResult(exit_code=0, stdout="secret\n")))
    execution = harness.service.execute(_command(persistence_depth=PersistenceDepth.METER))
    key = execution.call_identity.generate_key()
    assert execution.output_persisted is False
    assert harness.repository.find_current(key) is None
    assert harness.blob.puts == []


# --- end-to-end with the real stub adapter -----------------------------------


def test_caches_against_the_real_stub_adapter():
    """The deterministic stub makes the API path replayable: a second identical
    call is served from cache without calling the stub again."""
    harness = _Harness(StubApiClientAdapter())
    first = harness.service.execute(_command())
    second = harness.service.execute(_command())
    assert _stdout(first) == _stdout(second)
    assert harness.metrics.event_names() == ["record", "hit"]
