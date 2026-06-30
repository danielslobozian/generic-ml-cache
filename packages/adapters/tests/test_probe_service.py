# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ProbeService."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact, ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.probe.probe_status import ProbeStatus
from generic_ml_cache_core.application.port.inbound.probe_command import ProbeCommand
from generic_ml_cache_core.application.port.inbound.probe_use_case import ProbeUseCase
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.application.usecase.call_identity_building import build_call_identity
from generic_ml_cache_core.application.usecase.probe_service import ProbeService

from generic_ml_cache_adapters.adapter.out.persistence.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FakeFingerprint(FileFingerprintPort):
    def __init__(self) -> None:
        self.fingerprinted: list[str] = []

    def fingerprint(self, path: str) -> str:
        self.fingerprinted.append(path)
        return "fp_" + path


def _command(**overrides) -> ProbeCommand:
    base = dict(client="claude", model="sonnet", effort="high", context="ctx", prompt="do it")
    base.update(overrides)
    return ProbeCommand(**base)


def _store_current_execution(
    repository: InMemoryExecutionRepository, command: ProbeCommand
) -> None:
    identity = build_call_identity(FakeFingerprint(), command)
    repository.save(
        MlExecution(
            call_identity=identity,
            execution_state=ExecutionState.SUCCESS,
            execution_kind=ExecutionKind.LOCAL_MANAGED,
            output_persisted=True,
            artifacts=[
                Artifact(
                    artifact_type=ArtifactType.STDOUT, blob_key="k", size_bytes=2, content=b"hi"
                )
            ],
        )
    )


def _service(repository: InMemoryExecutionRepository) -> ProbeService:
    return ProbeService(FakeFingerprint(), repository)


# --- port wiring -------------------------------------------------------------


def test_inbound_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ProbeUseCase()  # type: ignore[abstract]


def test_service_implements_the_inbound_port():
    assert isinstance(_service(InMemoryExecutionRepository(FixedClock())), ProbeUseCase)


# --- verdicts ----------------------------------------------------------------


def test_miss_when_nothing_is_stored():
    report = _service(InMemoryExecutionRepository(FixedClock())).execute(_command())
    assert report.status is ProbeStatus.MISS
    assert report.execution is None
    assert report.execution_key


def test_hit_when_a_current_execution_exists():
    repository = InMemoryExecutionRepository(FixedClock())
    command = _command()
    _store_current_execution(repository, command)
    report = _service(repository).execute(command)
    assert report.status is ProbeStatus.HIT
    assert report.execution is not None


def test_non_cacheable_with_allow_paths():
    report = _service(InMemoryExecutionRepository(FixedClock())).execute(
        _command(allow_paths=["/workspace"])
    )
    assert report.status is ProbeStatus.NON_CACHEABLE
    assert report.execution is None


def test_scan_trust_makes_a_probe_cacheable_again():
    report = _service(InMemoryExecutionRepository(FixedClock())).execute(
        _command(allow_paths=["/workspace"], scan_trust=True)
    )
    assert report.status is ProbeStatus.MISS  # cacheable, just nothing recorded


# --- side-effect-free --------------------------------------------------------


def test_probe_records_nothing_in_the_repository():
    repository = InMemoryExecutionRepository(FixedClock())
    command = _command()
    _service(repository).execute(command)
    identity = build_call_identity(FakeFingerprint(), command)
    assert repository.find_all(identity.generate_key()) == []  # the probe stored nothing


# --- probe/run key agreement (the correctness guarantee) ---------------------


def test_probe_key_matches_a_run_key_for_the_same_inputs():
    probe_command = _command(input_file_paths=["/a"], client_args=["--flag"], grants=["net"])
    run_command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        client="claude",
        model="sonnet",
        effort="high",
        context="ctx",
        prompt="do it",
        input_file_paths=["/a"],
        client_args=["--flag"],
        grants=["net"],
    )
    probe_key = build_call_identity(FakeFingerprint(), probe_command).generate_key()
    run_key = build_call_identity(FakeFingerprint(), run_command).generate_key()
    assert probe_key == run_key
