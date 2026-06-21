# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ClientRunResult and GeneratedFile."""

from __future__ import annotations

import pytest

from generic_ml_cache_core.application.domain.model.run.client_run_result import (
    ClientRunResult,
    GeneratedFile,
)
from generic_ml_cache_core.application.domain.model.execution.execution_failure import FailureReason
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState


def test_minimal_result_needs_only_exit_code():
    result = ClientRunResult(exit_code=0)
    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.files == []
    assert result.token_usage is None


def test_result_can_carry_token_usage():
    from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage

    result = ClientRunResult(exit_code=0, token_usage=TokenUsage(input_tokens=10, output_tokens=3))
    assert result.token_usage.input_tokens == 10


def test_result_carries_streams():
    result = ClientRunResult(exit_code=0, stdout="the answer\n", stderr="a warning\n")
    assert result.stdout == "the answer\n"
    assert result.stderr == "a warning\n"


def test_result_carries_generated_files():
    result = ClientRunResult(
        exit_code=0,
        files=[GeneratedFile(name="out/result.txt", content=b"done")],
    )
    assert len(result.files) == 1
    assert result.files[0].name == "out/result.txt"
    assert result.files[0].content == b"done"


def test_generated_file_content_is_bytes():
    generated_file = GeneratedFile(name="blob.bin", content=b"\xff\x00")
    assert generated_file.content == b"\xff\x00"


def test_non_zero_exit_code_is_preserved():
    result = ClientRunResult(exit_code=2, stderr="failed\n")
    assert result.exit_code == 2


def test_is_frozen():
    result = ClientRunResult(exit_code=0)
    with pytest.raises(Exception):
        result.exit_code = 1  # type: ignore[misc]


# --- outcome interpretation (the rule lives on the result) -------------------


def test_zero_exit_succeeded():
    assert ClientRunResult(exit_code=0).succeeded is True


def test_nonzero_exit_did_not_succeed():
    assert ClientRunResult(exit_code=2).succeeded is False


def test_outcome_is_success_on_zero_exit():
    assert ClientRunResult(exit_code=0).outcome() is ExecutionState.SUCCESS


def test_outcome_is_failed_on_nonzero_exit():
    assert ClientRunResult(exit_code=1).outcome() is ExecutionState.FAILED


def test_failure_is_none_on_success():
    assert ClientRunResult(exit_code=0).failure() is None


def test_failure_describes_a_nonzero_exit():
    failure = ClientRunResult(exit_code=3).failure()
    assert failure is not None
    assert failure.reason is FailureReason.NONZERO_EXIT
    assert failure.exit_code == 3
    assert "3" in failure.message
