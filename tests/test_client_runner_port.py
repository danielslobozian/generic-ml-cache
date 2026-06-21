# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ClientRunnerPort contract."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.client_run_request import ClientRunRequest
from generic_ml_cache.application.domain.model.execution_output import ExecutionOutput
from generic_ml_cache.application.port.out.client_runner_port import ClientRunnerPort


def _make_request() -> ClientRunRequest:
    return ClientRunRequest(
        client="claude",
        model="sonnet",
        effort="high",
        context="",
        prompt="summarise this",
    )


class EchoClientRunner(ClientRunnerPort):
    """Minimal implementation that echoes the prompt as stdout."""

    def run(self, client_run_request: ClientRunRequest) -> ExecutionOutput:
        return ExecutionOutput(stdout=client_run_request.prompt, exit_code=0)


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ClientRunnerPort()  # type: ignore[abstract]


def test_run_returns_execution_output():
    runner = EchoClientRunner()
    execution_output = runner.run(_make_request())
    assert isinstance(execution_output, ExecutionOutput)


def test_run_output_reflects_request():
    runner = EchoClientRunner()
    execution_output = runner.run(_make_request())
    assert execution_output.stdout == "summarise this"
    assert execution_output.exit_code == 0


def test_run_accepts_client_run_request():
    runner = EchoClientRunner()
    request = ClientRunRequest(
        client="codex",
        model="o3",
        effort="medium",
        context="ctx",
        prompt="hello",
        grants=frozenset({"net"}),
    )
    execution_output = runner.run(request)
    assert execution_output.stdout == "hello"
