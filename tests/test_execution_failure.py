# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ExecutionFailure and FailureReason."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.execution.execution_failure import (
    ExecutionFailure,
    FailureReason,
)


def test_nonzero_exit_reason_value():
    assert FailureReason.NONZERO_EXIT.value == "nonzero_exit"


def test_reason_string_roundtrip():
    for failure_reason in FailureReason:
        assert FailureReason(failure_reason.value) is failure_reason


def test_local_failure_carries_exit_code():
    failure = ExecutionFailure(
        reason=FailureReason.NONZERO_EXIT,
        message="client exited with status 2",
        exit_code=2,
    )
    assert failure.reason is FailureReason.NONZERO_EXIT
    assert failure.exit_code == 2
    assert "status 2" in failure.message


def test_exit_code_is_optional_for_non_exit_causes():
    failure = ExecutionFailure(reason=FailureReason.NONZERO_EXIT, message="boom")
    assert failure.exit_code is None


def test_is_frozen():
    failure = ExecutionFailure(reason=FailureReason.NONZERO_EXIT, message="x")
    with pytest.raises(Exception):
        failure.message = "y"  # type: ignore[misc]
