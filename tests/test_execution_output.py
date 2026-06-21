# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ExecutionOutput."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.captured_file import CapturedFile
from generic_ml_cache.application.domain.model.execution_output import ExecutionOutput


def test_defaults():
    execution_output = ExecutionOutput()
    assert execution_output.stdout == ""
    assert execution_output.stderr == ""
    assert execution_output.exit_code == 0
    assert execution_output.files == []


def test_to_dict_round_trip():
    execution_output = ExecutionOutput(
        stdout="result\n",
        stderr="warning\n",
        exit_code=0,
        files=[CapturedFile(path="out/result.txt", content="done\n")],
    )
    reloaded = ExecutionOutput.from_dict(execution_output.to_dict())
    assert reloaded == execution_output


def test_from_dict_missing_keys_use_defaults():
    execution_output = ExecutionOutput.from_dict({})
    assert execution_output.stdout == ""
    assert execution_output.exit_code == 0
    assert execution_output.files == []


def test_from_dict_files_are_deserialized():
    execution_output_dict = {
        "stdout": "hi",
        "stderr": "",
        "exit_code": 0,
        "files": [{"path": "out/a.txt", "content": "hello", "encoding": "utf-8"}],
    }
    execution_output = ExecutionOutput.from_dict(execution_output_dict)
    assert len(execution_output.files) == 1
    assert execution_output.files[0].path == "out/a.txt"
    assert execution_output.files[0].content == "hello"


def test_non_zero_exit_code_preserved():
    execution_output = ExecutionOutput(exit_code=1)
    reloaded = ExecutionOutput.from_dict(execution_output.to_dict())
    assert reloaded.exit_code == 1


def test_token_usage_is_not_a_field():
    assert not hasattr(ExecutionOutput, "usage")
    assert not hasattr(ExecutionOutput, "token_usage")


def test_is_frozen():
    execution_output = ExecutionOutput(stdout="x")
    with pytest.raises(Exception):
        execution_output.stdout = "y"  # type: ignore[misc]
