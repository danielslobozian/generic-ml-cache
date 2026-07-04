# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the composition root.

These exercise the whole wired stack end-to-end — the real filesystem fingerprint,
client runner, blob store, SQLite repository, and metrics — with the fake client.
"""

from __future__ import annotations

import sqlite3

from generic_ml_cache_bootstrap.discovery.composition import execution_kind_for
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)

from generic_ml_cache_cli._compose import build_use_cases


def _factory(tmp_path):
    db_path = tmp_path / "executions.sqlite3"

    def _connect():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(db_path))

    return _connect


def _stdout(execution) -> bytes | None:
    for artifact in execution.artifacts:
        if artifact.artifact_type is ArtifactType.STDOUT:
            return artifact.content
    return None


def _repo(tmp_path):
    # White-box: build the repository out-port directly (it is no longer on the
    # narrowed ApplicationApi) to assert the stored audit trail.
    from generic_ml_cache_adapters.adapter.outbound.clock.system_clock import SystemClock
    from generic_ml_cache_adapters.adapter.outbound.persistence.execution_repository import (
        ExecutionRepository,
    )

    return ExecutionRepository(_factory(tmp_path), SystemClock())


def test_managed_records_then_replays_through_the_whole_stack(tmp_path):
    wired = build_use_cases(_factory(tmp_path), tmp_path, client="fake")
    command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        client="fake",
        model="m",
        effort="",
        context="",
        prompt="STDOUT hello-world",
    )

    first = wired.run_ml.execute(command)
    assert first.execution_state is ExecutionState.SUCCESS
    assert first.execution_kind is ExecutionKind.LOCAL_MANAGED
    assert first.output_persisted is True
    assert b"hello-world" in _stdout(first)

    second = wired.run_ml.execute(command)
    assert _stdout(second) == _stdout(first)  # replay reproduces the output

    key = first.call_identity.generate_key()
    assert len(_repo(tmp_path).find_all(key)) == 2  # IN_PROGRESS + SUCCESS from one real run
    assert wired.event_counts.event_counts() == {"record": 1, "hit": 1}


def test_managed_durable_across_a_fresh_wiring(tmp_path):
    command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        client="fake",
        model="m",
        effort="",
        context="",
        prompt="STDOUT durable",
    )
    build_use_cases(_factory(tmp_path), tmp_path, client="fake").run_ml.execute(command)
    # A brand-new wiring on the same store serves the prior run from disk.
    replay = build_use_cases(_factory(tmp_path), tmp_path, client="fake").run_ml.execute(command)
    assert b"durable" in _stdout(replay)
    key = replay.call_identity.generate_key()
    assert len(_repo(tmp_path).find_all(key)) == 2


def test_passthrough_records_then_replays(tmp_path):
    wired = build_use_cases(_factory(tmp_path), tmp_path, client="fake")
    command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.LOCAL_PASSTHROUGH,
        client="fake",
        model="",
        native_args=["-c", "print('pt')"],
    )
    first = wired.run_ml.execute(command)
    assert first.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH
    assert b"pt" in _stdout(first)
    wired.run_ml.execute(command)
    assert wired.event_counts.event_counts() == {"record": 1, "hit": 1}


def test_api_records_then_replays_with_the_stub(tmp_path):
    wired = build_use_cases(_factory(tmp_path), tmp_path)
    command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.API, client="openai", model="gpt-x", context="", prompt="hi"
    )
    first = wired.run_ml.execute(command)
    assert first.execution_kind is ExecutionKind.API
    assert first.token_usage is not None
    second = wired.run_ml.execute(command)
    assert _stdout(second) == _stdout(first)
    assert wired.event_counts.event_counts() == {"record": 1, "hit": 1}


def test_api_client_routes_to_api_adapter(tmp_path):
    wired = build_use_cases(_factory(tmp_path), tmp_path, client="fake-api")
    command = RunMlExecutionCommand(
        execution_kind=execution_kind_for("fake-api"),
        client="fake-api",
        model="m",
        context="",
        prompt="hello",
    )
    first = wired.run_ml.execute(command)
    assert first.execution_kind is ExecutionKind.API
    assert first.token_usage is not None
    second = wired.run_ml.execute(command)
    assert _stdout(second) == _stdout(first)
    assert wired.event_counts.event_counts() == {"record": 1, "hit": 1}
