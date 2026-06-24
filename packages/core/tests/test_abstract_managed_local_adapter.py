# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for AbstractManagedLocalAdapter — end-to-end against the fake client."""

from __future__ import annotations

import base64

from generic_ml_cache_core.adapter.out.client.abstract_managed_local_adapter import (
    AbstractManagedLocalAdapter,
)
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.client_runner_port import ClientRunnerPort


def _request(prompt: str) -> MlRequest:
    return MlRequest(model="m", effort="", context="", prompt=prompt)


def _fake_adapter():
    """Return a fresh FakeAdapter instance (registered in conftest)."""
    from generic_ml_cache_core.adapter.out.client.registry import get_adapter
    cls = type(get_adapter("fake"))
    return cls()


def test_fake_adapter_is_a_client_runner_port():
    assert isinstance(_fake_adapter(), ClientRunnerPort)


def test_fake_adapter_is_an_abstract_managed_local_adapter():
    assert isinstance(_fake_adapter(), AbstractManagedLocalAdapter)


def test_captures_stdout_and_a_zero_exit():
    result = _fake_adapter().run(_request("STDOUT hello-from-fake"))
    assert isinstance(result, ClientRunResult)
    assert "hello-from-fake" in result.stdout
    assert result.exit_code == 0
    assert result.succeeded is True


def test_captures_a_nonzero_exit():
    result = _fake_adapter().run(_request("EXIT 3"))
    assert result.exit_code == 3
    assert result.succeeded is False


def test_captures_a_generated_file_as_an_artifact():
    encoded = base64.b64encode(b"file body").decode("ascii")
    result = _fake_adapter().run(_request(f"WRITE out/result.txt {encoded}"))
    produced = [f for f in result.files if f.name == "out/result.txt"]
    assert len(produced) == 1
    assert produced[0].content == b"file body"


def test_no_files_when_the_client_writes_none():
    result = _fake_adapter().run(_request("STDOUT just-text"))
    assert result.files == []
