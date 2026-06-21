# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for MlExecution aggregate."""

from __future__ import annotations

from generic_ml_cache.application.domain.model.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.execution_kind import ExecutionKind
from generic_ml_cache.application.domain.model.execution_output import ExecutionOutput
from generic_ml_cache.application.domain.model.execution_state import ExecutionState
from generic_ml_cache.application.domain.model.ml_execution import MlExecution
from generic_ml_cache.application.domain.model.token_usage import TokenUsage


def _make_identity() -> CallIdentity:
    return CallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="ctx_sha",
        prompt_fingerprint="prompt_sha",
    )


def test_in_progress_execution_has_no_output():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.IN_PROGRESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
    )
    assert execution.execution_output is None
    assert execution.token_usage is None
    assert execution.output_persisted is False


def test_successful_execution_carries_output():
    execution_output = ExecutionOutput(stdout="result\n", exit_code=0)
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        execution_output=execution_output,
    )
    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.execution_output.stdout == "result\n"
    assert execution.output_persisted is True


def test_failed_execution_state():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.FAILED,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
        execution_output=ExecutionOutput(exit_code=1, stderr="error\n"),
    )
    assert execution.execution_state is ExecutionState.FAILED
    assert execution.execution_output.exit_code == 1


def test_token_usage_is_separate_from_output():
    token_usage = TokenUsage(input_tokens=100, output_tokens=42)
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        execution_output=ExecutionOutput(stdout="ok"),
        token_usage=token_usage,
    )
    assert execution.token_usage.input_tokens == 100
    assert execution.execution_output.stdout == "ok"


def test_passthrough_execution_can_succeed_without_persisting():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_PASSTHROUGH,
        output_persisted=False,
        execution_output=ExecutionOutput(stdout="native output\n"),
    )
    assert execution.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH
    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.output_persisted is False


def test_api_execution_kind():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.IN_PROGRESS,
        execution_kind=ExecutionKind.API,
        output_persisted=False,
    )
    assert execution.execution_kind is ExecutionKind.API


def test_call_identity_is_accessible():
    identity = _make_identity()
    execution = MlExecution(
        call_identity=identity,
        execution_state=ExecutionState.IN_PROGRESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
    )
    assert execution.call_identity is identity
    assert execution.call_identity.generate_key() == identity.generate_key()
