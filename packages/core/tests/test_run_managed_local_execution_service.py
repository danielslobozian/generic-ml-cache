# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunManagedLocalExecutionService."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

import pytest

from generic_ml_cache_core.adapter.out.persistence.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.client_run_request import ClientRunRequest
from generic_ml_cache_core.application.domain.model.run.client_run_result import (
    ClientRunResult,
    GeneratedFile,
)
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.client_runner_port import ClientRunnerPort
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.port.inbound.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_managed_local_execution_use_case import (
    RunManagedLocalExecutionUseCase,
)
from generic_ml_cache_core.application.usecase.run_managed_local_execution_service import (
    RunManagedLocalExecutionService,
)
from generic_ml_cache_core.common.errors import ArtifactBlobMissing, CacheMiss


# --- fakes -------------------------------------------------------------------


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FakeFileFingerprint(FileFingerprintPort):
    def __init__(self) -> None:
        self.fingerprinted: List[str] = []

    def fingerprint(self, path: str) -> str:
        self.fingerprinted.append(path)
        return "fp_" + path


class FakeClientRunner(ClientRunnerPort):
    def __init__(self, *results: ClientRunResult) -> None:
        self._results = list(results) or [ClientRunResult(exit_code=0, stdout="the answer\n")]
        self.calls: List[ClientRunRequest] = []

    def run(self, client_run_request: ClientRunRequest) -> ClientRunResult:
        self.calls.append(client_run_request)
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
        self.events: List[str] = []

    def record_event(self, event, *, execution_key, client, model, effort) -> None:
        self.events.append(event)

    def hit_counts_by_key(self) -> Dict[str, int]:
        return {}

    def event_counts(self) -> Dict[str, int]:
        return {}

    def last_access(self) -> Dict[str, float]:
        return {}


# --- builders ----------------------------------------------------------------


def _command(**overrides) -> RunManagedLocalExecutionCommand:
    base = dict(client="claude", model="sonnet", effort="high", context="ctx", prompt="do it")
    base.update(overrides)
    return RunManagedLocalExecutionCommand(**base)


class _Harness:
    def __init__(self, *results: ClientRunResult) -> None:
        self.fingerprint = FakeFileFingerprint()
        self.runner = FakeClientRunner(*results)
        self.blob = FakeBlobStore()
        self.repository = InMemoryExecutionRepository(clock=FixedClock())
        self.metrics = FakeMetrics()
        self.use_case = RunManagedLocalExecutionService(
            file_fingerprint=self.fingerprint,
            client_runner=self.runner,
            blob_store=self.blob,
            repository=self.repository,
            metrics=self.metrics,
        )


def _stdout(execution) -> Optional[bytes]:
    for artifact in execution.artifacts:
        if artifact.artifact_type is ArtifactType.STDOUT:
            return artifact.content
    return None


# --- inbound port wiring -----------------------------------------------------


def test_inbound_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        RunManagedLocalExecutionUseCase()  # type: ignore[abstract]


def test_service_implements_the_inbound_port():
    assert isinstance(_Harness().use_case, RunManagedLocalExecutionUseCase)


# --- miss / record -----------------------------------------------------------


def test_miss_runs_records_and_returns_hydrated_success():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    execution = harness.use_case.execute(_command())

    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.output_persisted is True
    assert execution.failure is None
    assert _stdout(execution) == b"answer\n"  # returned hydrated
    assert len(harness.runner.calls) == 1
    assert harness.metrics.events == ["record"]


def test_miss_stores_output_to_blob_and_repository():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    execution = harness.use_case.execute(_command())
    key = execution.call_identity.generate_key()

    assert harness.repository.find_current(key) is not None
    # stdout + stderr blobs are stored, content-addressed
    assert len(harness.blob.store) >= 1
    assert harness.repository.find_current(key).artifacts[0].content is None  # stored dehydrated


# --- hit / replay ------------------------------------------------------------


def test_second_identical_call_is_served_from_cache_without_running():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    harness.use_case.execute(_command())
    second = harness.use_case.execute(_command())

    assert len(harness.runner.calls) == 1  # client ran only once
    assert harness.metrics.events == ["record", "hit"]
    assert _stdout(second) == b"answer\n"  # hydrated from the blob store


def test_a_different_prompt_misses_and_runs_again():
    harness = _Harness()
    harness.use_case.execute(_command(prompt="first"))
    harness.use_case.execute(_command(prompt="second"))
    assert len(harness.runner.calls) == 2
    assert harness.metrics.events == ["record", "record"]


# --- input file fingerprinting -----------------------------------------------


def test_input_files_are_fingerprinted_through_the_port():
    harness = _Harness()
    harness.use_case.execute(_command(input_file_paths=["/src/a.py", "/src/b.py"]))
    assert harness.fingerprint.fingerprinted == ["/src/a.py", "/src/b.py"]


def test_input_files_change_the_identity():
    harness = _Harness()
    harness.use_case.execute(_command())
    harness.use_case.execute(_command(input_file_paths=["/src/a.py"]))
    assert len(harness.runner.calls) == 2  # different key -> a real second run


# --- refresh -----------------------------------------------------------------


def test_refresh_always_runs_and_supersedes():
    harness = _Harness(
        ClientRunResult(exit_code=0, stdout="old\n"),
        ClientRunResult(exit_code=0, stdout="new\n"),
    )
    first = harness.use_case.execute(_command())
    second = harness.use_case.execute(_command(cache_mode=CacheMode.REFRESH))
    key = first.call_identity.generate_key()

    assert len(harness.runner.calls) == 2
    assert _stdout(second) == b"new\n"
    assert _stdout(harness.use_case.execute(_command())) == b"new\n"  # cache now serves new
    assert len(harness.repository.find_all(key)) == 2  # append-only history


# --- offline -----------------------------------------------------------------


def test_offline_miss_raises_and_does_not_run():
    harness = _Harness()
    with pytest.raises(CacheMiss):
        harness.use_case.execute(_command(cache_mode=CacheMode.OFFLINE))
    assert harness.runner.calls == []
    assert harness.metrics.events == ["miss"]


def test_offline_hit_serves_from_cache():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    harness.use_case.execute(_command())  # populate
    served = harness.use_case.execute(_command(cache_mode=CacheMode.OFFLINE))
    assert len(harness.runner.calls) == 1
    assert _stdout(served) == b"answer\n"
    assert harness.metrics.events == ["record", "hit"]


# --- failure handling --------------------------------------------------------


def test_failed_call_is_not_stored_by_default():
    harness = _Harness(ClientRunResult(exit_code=2, stderr="boom\n"))
    execution = harness.use_case.execute(_command())
    key = execution.call_identity.generate_key()

    assert execution.execution_state is ExecutionState.FAILED
    assert execution.output_persisted is False
    assert execution.failure is not None
    assert execution.failure.exit_code == 2
    assert harness.repository.find_current(key) is None  # not cached
    assert harness.metrics.events == ["run"]


def test_failed_call_is_stored_with_record_on_error():
    harness = _Harness(ClientRunResult(exit_code=2, stderr="boom\n"))
    execution = harness.use_case.execute(_command(record_on_error=True))
    key = execution.call_identity.generate_key()

    assert execution.execution_state is ExecutionState.FAILED
    assert execution.output_persisted is True
    assert harness.repository.find_current(key) is None  # a failure is not "current/servable"
    assert harness.repository.find_all(key) != []  # but it is recorded
    assert harness.metrics.events == ["record"]


# --- persist_output ----------------------------------------------------------


def test_persist_output_false_runs_but_stores_nothing():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="secret\n"))
    execution = harness.use_case.execute(_command(persist_output=False))
    key = execution.call_identity.generate_key()

    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.output_persisted is False
    assert _stdout(execution) == b"secret\n"  # caller still gets the output
    assert harness.repository.find_current(key) is None
    assert harness.blob.puts == []  # nothing written to the blob store
    assert harness.metrics.events == ["run"]


# --- allow-paths (uncacheable) -----------------------------------------------


def test_allow_paths_make_the_call_uncacheable():
    harness = _Harness()
    execution = harness.use_case.execute(_command(allow_paths=["/workspace"]))
    key = execution.call_identity.generate_key()

    assert execution.output_persisted is False
    assert harness.repository.find_current(key) is None
    assert harness.metrics.events == ["run"]


def test_scan_trust_makes_an_allow_path_call_cacheable_again():
    harness = _Harness()
    execution = harness.use_case.execute(_command(allow_paths=["/workspace"], scan_trust=True))
    key = execution.call_identity.generate_key()

    assert execution.output_persisted is True
    assert harness.repository.find_current(key) is not None
    assert harness.metrics.events == ["record"]


def test_allow_paths_offline_raises():
    harness = _Harness()
    with pytest.raises(CacheMiss):
        harness.use_case.execute(_command(allow_paths=["/workspace"], cache_mode=CacheMode.OFFLINE))
    assert harness.runner.calls == []


# --- artifacts ---------------------------------------------------------------


def test_generated_files_become_output_file_artifacts():
    harness = _Harness(
        ClientRunResult(
            exit_code=0,
            stdout="done\n",
            files=[GeneratedFile(name="out/result.txt", content=b"result data")],
        )
    )
    execution = harness.use_case.execute(_command())
    file_artifacts = [a for a in execution.artifacts if a.artifact_type is ArtifactType.OUTPUT_FILE]
    assert len(file_artifacts) == 1
    assert file_artifacts[0].name == "out/result.txt"
    assert file_artifacts[0].content == b"result data"


def test_binary_output_file_is_marked_binary():
    harness = _Harness(
        ClientRunResult(
            exit_code=0,
            files=[GeneratedFile(name="blob.bin", content=b"\xff\xfe\x00")],
        )
    )
    execution = harness.use_case.execute(_command())
    binary_artifact = [a for a in execution.artifacts if a.name == "blob.bin"][0]
    assert binary_artifact.encoding == "binary"


def test_every_call_has_stdout_and_stderr_artifacts():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="out", stderr="err"))
    execution = harness.use_case.execute(_command())
    types = {a.artifact_type for a in execution.artifacts}
    assert ArtifactType.STDOUT in types
    assert ArtifactType.STDERR in types


# --- hydration failure -------------------------------------------------------


def test_hit_with_missing_blob_fails_loud():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    harness.use_case.execute(_command())
    harness.blob.store.clear()  # the bytes vanish out of band
    with pytest.raises(ArtifactBlobMissing):
        harness.use_case.execute(_command())


# --- identity dimensions -----------------------------------------------------


def test_client_args_change_the_identity():
    harness = _Harness()
    harness.use_case.execute(_command())
    harness.use_case.execute(_command(client_args=["--flag"]))
    assert len(harness.runner.calls) == 2


def test_grants_change_the_identity():
    harness = _Harness()
    harness.use_case.execute(_command())
    harness.use_case.execute(_command(grants=["net"]))
    assert len(harness.runner.calls) == 2


# --- tags (non-identity metadata) --------------------------------------------


def test_tags_are_normalized_and_applied_to_the_recorded_execution():
    harness = _Harness(ClientRunResult(exit_code=0, stdout="answer\n"))
    execution = harness.use_case.execute(_command(tags=["  ticket ", "scan", "ticket", "", "scan"]))
    key = execution.call_identity.generate_key()
    assert harness.repository.tags_for(key) == ["scan", "ticket"]


def test_a_hit_accumulates_new_tags_onto_the_entry():
    harness = _Harness()
    first = harness.use_case.execute(_command(tags=["scan"]))
    key = first.call_identity.generate_key()
    harness.use_case.execute(_command(tags=["ticket"]))  # same input -> a hit
    # Tags are out of the key (still one run) and accumulate on the entry.
    assert len(harness.runner.calls) == 1
    assert harness.metrics.events == ["record", "hit"]
    assert harness.repository.tags_for(key) == ["scan", "ticket"]
