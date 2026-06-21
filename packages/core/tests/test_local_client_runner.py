# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for LocalClientRunner — end-to-end against the fake client adapter."""

from __future__ import annotations

import base64

from generic_ml_cache_core.adapter.out.client.local_client_runner import LocalClientRunner
from generic_ml_cache_core.application.domain.model.run.client_run_request import ClientRunRequest
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.port.out.client_runner_port import ClientRunnerPort


def _request(prompt: str) -> ClientRunRequest:
    return ClientRunRequest(client="fake", model="m", effort="", context="", prompt=prompt)


def test_is_a_client_runner_port():
    assert isinstance(LocalClientRunner(), ClientRunnerPort)


def test_captures_stdout_and_a_zero_exit():
    result = LocalClientRunner().run(_request("STDOUT hello-from-fake"))
    assert isinstance(result, ClientRunResult)
    assert "hello-from-fake" in result.stdout
    assert result.exit_code == 0
    assert result.succeeded is True


def test_captures_a_nonzero_exit():
    result = LocalClientRunner().run(_request("EXIT 3"))
    assert result.exit_code == 3
    assert result.succeeded is False


def test_captures_a_generated_file_as_an_artifact():
    encoded = base64.b64encode(b"file body").decode("ascii")
    result = LocalClientRunner().run(_request(f"WRITE out/result.txt {encoded}"))
    produced = [generated for generated in result.files if generated.name == "out/result.txt"]
    assert len(produced) == 1
    assert produced[0].content == b"file body"


def test_no_files_when_the_client_writes_none():
    result = LocalClientRunner().run(_request("STDOUT just-text"))
    assert result.files == []
