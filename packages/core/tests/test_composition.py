# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for the composition root.

These exercise the whole wired stack end-to-end — the real filesystem fingerprint,
client runner, blob store, SQLite repository, and metrics — with the fake client.
"""

from __future__ import annotations

from typing import Optional

from generic_ml_cache_core.adapter.inbound.composition import build_use_cases
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.run.message import Message
from generic_ml_cache_core.application.port.inbound.run_api_execution_command import (
    RunApiExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_passthrough_execution_command import (
    RunPassthroughExecutionCommand,
)


def _stdout(execution) -> Optional[bytes]:
    for artifact in execution.artifacts:
        if artifact.artifact_type is ArtifactType.STDOUT:
            return artifact.content
    return None


def test_managed_records_then_replays_through_the_whole_stack(tmp_path):
    wired = build_use_cases(tmp_path)
    command = RunManagedLocalExecutionCommand(
        client="fake", model="m", effort="", context="", prompt="STDOUT hello-world"
    )

    first = wired.run_managed.execute(command)
    assert first.execution_state is ExecutionState.SUCCESS
    assert first.execution_kind is ExecutionKind.LOCAL_MANAGED
    assert first.output_persisted is True
    assert b"hello-world" in _stdout(first)

    second = wired.run_managed.execute(command)
    assert _stdout(second) == _stdout(first)  # replay reproduces the output

    key = first.call_identity.generate_key()
    assert len(wired.repository.find_all(key)) == 1  # the second was a hit, not a new run
    assert wired.metrics.event_counts() == {"record": 1, "hit": 1}


def test_managed_durable_across_a_fresh_wiring(tmp_path):
    command = RunManagedLocalExecutionCommand(
        client="fake", model="m", effort="", context="", prompt="STDOUT durable"
    )
    build_use_cases(tmp_path).run_managed.execute(command)
    # A brand-new wiring on the same store serves the prior run from disk.
    replay = build_use_cases(tmp_path).run_managed.execute(command)
    assert b"durable" in _stdout(replay)
    key = replay.call_identity.generate_key()
    assert len(build_use_cases(tmp_path).repository.find_all(key)) == 1


def test_passthrough_records_then_replays(tmp_path):
    wired = build_use_cases(tmp_path)
    command = RunPassthroughExecutionCommand(client="fake", native_args=["-c", "print('pt')"])
    first = wired.run_passthrough.execute(command)
    assert first.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH
    assert b"pt" in _stdout(first)
    wired.run_passthrough.execute(command)
    assert wired.metrics.event_counts() == {"record": 1, "hit": 1}


def test_api_records_then_replays_with_the_stub(tmp_path):
    wired = build_use_cases(tmp_path)
    command = RunApiExecutionCommand(
        provider="openai", model="gpt-x", messages=[Message(role="user", content="hi")]
    )
    first = wired.run_api.execute(command)
    assert first.execution_kind is ExecutionKind.API
    assert first.token_usage is not None
    second = wired.run_api.execute(command)
    assert _stdout(second) == _stdout(first)
    assert wired.metrics.event_counts() == {"record": 1, "hit": 1}
