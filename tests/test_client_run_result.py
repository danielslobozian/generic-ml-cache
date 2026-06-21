# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ClientRunResult and GeneratedFile."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.client_run_result import (
    ClientRunResult,
    GeneratedFile,
)


def test_minimal_result_needs_only_exit_code():
    result = ClientRunResult(exit_code=0)
    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.files == []


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
