# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ApiClientPort contract and the stub adapter."""

from __future__ import annotations

import pytest

from generic_ml_cache_adapters.adapter.out.api.stub_api_client_adapter import StubApiClientAdapter
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort


def _request(prompt: str = "summarise this") -> MlRequest:
    return MlRequest(model="gpt-x", effort="", context="", prompt=prompt)


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ApiClientPort()  # type: ignore[abstract]


def test_stub_is_an_api_client_port():
    assert isinstance(StubApiClientAdapter(), ApiClientPort)


def test_stub_returns_a_client_run_result_with_no_files():
    result = StubApiClientAdapter().run(_request())
    assert isinstance(result, ClientRunResult)
    assert result.exit_code == 0
    assert result.files == []


def test_stub_reply_reflects_model_and_prompt():
    result = StubApiClientAdapter().run(_request())
    assert "gpt-x" in result.stdout
    assert "summarise this" in result.stdout


def test_stub_is_deterministic():
    first = StubApiClientAdapter().run(_request())
    second = StubApiClientAdapter().run(_request())
    assert first.stdout == second.stdout
    assert first.token_usage == second.token_usage


def test_stub_reports_token_usage():
    result = StubApiClientAdapter().run(_request())
    assert result.token_usage is not None
    assert result.token_usage.input_tokens == len("summarise this")


def test_stub_accepts_effort_without_error():
    result = StubApiClientAdapter().run(
        MlRequest(model="gpt-x", effort="high", context="", prompt="summarise this")
    )
    assert result.exit_code == 0
