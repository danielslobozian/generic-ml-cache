# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for PassthroughRunnerPort contract."""

from __future__ import annotations

from typing import List

import pytest

from generic_ml_cache.application.domain.model.client_run_result import ClientRunResult
from generic_ml_cache.application.port.out.passthrough_runner_port import PassthroughRunnerPort


class EchoPassthroughRunner(PassthroughRunnerPort):
    def run(self, client: str, native_args: List[str]) -> ClientRunResult:
        return ClientRunResult(exit_code=0, stdout=" ".join(native_args))


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        PassthroughRunnerPort()  # type: ignore[abstract]


def test_run_returns_a_client_run_result():
    result = EchoPassthroughRunner().run("claude", ["--help"])
    assert isinstance(result, ClientRunResult)
    assert result.stdout == "--help"
    assert result.files == []
