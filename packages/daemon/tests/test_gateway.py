# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for POST /gateway/claude/{session_id}/v1/messages."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from generic_ml_cache_core.application.domain.model.gateway.gateway_response import GatewayResponse
from generic_ml_cache_core.application.port.inbound.run_ml_gateway_command import (
    RunMlGatewayCommand,
)
from starlette.testclient import TestClient

_SESSION = "test-session-abc"
_URL = f"/gateway/claude/{_SESSION}/v1/messages"

_ANTHROPIC_BODY = json.dumps(
    {
        "id": "msg_01XFDUDYJgAACzvnptvVoYEL",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello!"}],
        "model": "claude-opus-4-8",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
).encode()

_SINGLE_TURN = {
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "Hello!"}],
}


def _make_gateway_response(
    cache_hit: bool = False,
    status_code: int = 200,
    body: bytes = _ANTHROPIC_BODY,
) -> GatewayResponse:
    return GatewayResponse(
        response_body_bytes=body,
        status_code=status_code,
        cache_hit=cache_hit,
    )


def _patched_client(tmp_path: Path, gateway_response: GatewayResponse) -> TestClient:
    from generic_ml_cache_daemon.app import create_app

    app = create_app(tmp_path)
    app.state.wired.run_gateway.execute = MagicMock(return_value=gateway_response)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Happy path — status code and response body
# ---------------------------------------------------------------------------


def test_gateway_returns_200(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        assert tc.post(_URL, json=_SINGLE_TURN).status_code == 200


def test_gateway_returns_response_body_verbatim(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        assert tc.post(_URL, json=_SINGLE_TURN).content == _ANTHROPIC_BODY


def test_gateway_x_cache_hit_false_on_miss(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response(cache_hit=False)) as tc:
        assert tc.post(_URL, json=_SINGLE_TURN).headers["x-cache-hit"] == "false"


def test_gateway_x_cache_hit_true_on_hit(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response(cache_hit=True)) as tc:
        assert tc.post(_URL, json=_SINGLE_TURN).headers["x-cache-hit"] == "true"


# ---------------------------------------------------------------------------
# Command construction — verify what the route passes to the use case
# ---------------------------------------------------------------------------


def test_gateway_command_carries_api_token(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        tc.post(_URL, json=_SINGLE_TURN, headers={"x-api-key": "sk-ant-test"})
        command: RunMlGatewayCommand = tc.app.state.wired.run_gateway.execute.call_args[0][0]
        assert command.api_token == "sk-ant-test"


def test_gateway_command_carries_model(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        tc.post(_URL, json=_SINGLE_TURN)
        command: RunMlGatewayCommand = tc.app.state.wired.run_gateway.execute.call_args[0][0]
        assert command.gateway_request.model == "claude-opus-4-8"


def test_gateway_command_carries_messages(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        tc.post(_URL, json=_SINGLE_TURN)
        command: RunMlGatewayCommand = tc.app.state.wired.run_gateway.execute.call_args[0][0]
        assert command.gateway_request.messages[0]["role"] == "user"


def test_gateway_command_carries_system(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        body = {**_SINGLE_TURN, "system": "You are a helpful assistant."}
        tc.post(_URL, json=body)
        command: RunMlGatewayCommand = tc.app.state.wired.run_gateway.execute.call_args[0][0]
        assert command.gateway_request.system == "You are a helpful assistant."


def test_gateway_command_keeps_extra_request_fields(tmp_path: Path) -> None:
    # extra="allow": temperature/tools/… survive into the body the gateway forwards
    # and keys — the proxy never drops a field the caller sent. The gmlcache
    # session id rides in the URL, not the body, so it is excluded.
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        body = {**_SINGLE_TURN, "temperature": 0.3, "tools": [{"name": "search"}]}
        tc.post(_URL, json=body)
        command: RunMlGatewayCommand = tc.app.state.wired.run_gateway.execute.call_args[0][0]
        assert command.gateway_request.body["temperature"] == 0.3
        assert command.gateway_request.body["tools"] == [{"name": "search"}]
        assert "session_id" not in command.gateway_request.body


def test_gateway_session_id_from_url_path(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        tc.post(_URL, json=_SINGLE_TURN)
        command: RunMlGatewayCommand = tc.app.state.wired.run_gateway.execute.call_args[0][0]
        assert command.session_id == _SESSION


# ---------------------------------------------------------------------------
# Multi-turn and extra fields
# ---------------------------------------------------------------------------


def test_gateway_multi_turn_returns_200(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        multi_turn = {
            "model": "claude-opus-4-8",
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
                {"role": "user", "content": "How are you?"},
            ],
        }
        assert tc.post(_URL, json=multi_turn).status_code == 200


def test_gateway_extra_fields_ignored(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        body = {**_SINGLE_TURN, "metadata": {"user_id": "abc"}, "stream": False}
        assert tc.post(_URL, json=body).status_code == 200


# ---------------------------------------------------------------------------
# Upstream error forwarding
# ---------------------------------------------------------------------------


def test_gateway_forwards_upstream_4xx_status(tmp_path: Path) -> None:
    error_body = json.dumps({"type": "error", "error": {"type": "rate_limit_error"}}).encode()
    with _patched_client(tmp_path, _make_gateway_response(status_code=429, body=error_body)) as tc:
        response = tc.post(_URL, json=_SINGLE_TURN)
        assert response.status_code == 429
        assert response.content == error_body


# ---------------------------------------------------------------------------
# Validation — missing required field
# ---------------------------------------------------------------------------


def test_gateway_missing_model_returns_422(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_gateway_response()) as tc:
        assert (
            tc.post(_URL, json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 422
        )
