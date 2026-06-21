# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for MlExecution aggregate."""

from __future__ import annotations

from datetime import datetime, timezone

from generic_ml_cache.application.domain.model.artifact import Artifact, ArtifactType
from generic_ml_cache.application.domain.model.managed_call_identity import ManagedCallIdentity
from generic_ml_cache.application.domain.model.execution_failure import (
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache.application.domain.model.execution_kind import ExecutionKind
from generic_ml_cache.application.domain.model.execution_state import ExecutionState
from generic_ml_cache.application.domain.model.ml_execution import MlExecution
from generic_ml_cache.application.domain.model.token_usage import TokenUsage


def _make_identity() -> ManagedCallIdentity:
    return ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="ctx_sha",
        prompt_fingerprint="prompt_sha",
    )


def _stdout_artifact(content: bytes = b"result\n") -> Artifact:
    return Artifact(
        artifact_type=ArtifactType.STDOUT,
        blob_key="stdout_key",
        size_bytes=len(content),
        content=content,
    )


def test_in_progress_execution_has_no_artifacts_or_failure():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.IN_PROGRESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
    )
    assert execution.artifacts == []
    assert execution.token_usage is None
    assert execution.failure is None
    assert execution.superseded_at is None
    assert execution.output_persisted is False


def test_successful_execution_carries_artifacts():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        artifacts=[_stdout_artifact()],
    )
    assert execution.execution_state is ExecutionState.SUCCESS
    assert execution.artifacts[0].artifact_type is ArtifactType.STDOUT
    assert execution.artifacts[0].content == b"result\n"
    assert execution.failure is None


def test_failed_execution_carries_a_failure_not_an_exit_code():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.FAILED,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
        failure=ExecutionFailure(
            reason=FailureReason.NONZERO_EXIT, message="exit 1", exit_code=1
        ),
    )
    assert execution.execution_state is ExecutionState.FAILED
    assert execution.failure.exit_code == 1
    assert not hasattr(execution, "exit_code")


def test_token_usage_is_separate_from_artifacts():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        artifacts=[_stdout_artifact(b"ok")],
        token_usage=TokenUsage(input_tokens=100, output_tokens=42),
    )
    assert execution.token_usage.input_tokens == 100
    assert execution.artifacts[0].content == b"ok"


def test_passthrough_execution_can_succeed_without_persisting():
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_PASSTHROUGH,
        output_persisted=False,
        artifacts=[_stdout_artifact(b"native output\n")],
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


def test_superseded_at_marks_a_stale_execution():
    stale_moment = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        artifacts=[_stdout_artifact()],
        superseded_at=stale_moment,
    )
    assert execution.superseded_at == stale_moment


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


def test_dehydrated_execution_has_artifacts_without_content():
    dehydrated_artifact = Artifact(
        artifact_type=ArtifactType.STDOUT, blob_key="k", size_bytes=7
    )
    execution = MlExecution(
        call_identity=_make_identity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        artifacts=[dehydrated_artifact],
    )
    assert execution.artifacts[0].is_hydrated is False
    assert execution.artifacts[0].blob_key == "k"
