# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for POST /gateway/claude/v1/messages."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from starlette.testclient import TestClient

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import (
    ExecutionState,
)
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution

_URL = "/gateway/claude/v1/messages"


def _make_execution(stdout: str = "Hello!", state: ExecutionState = ExecutionState.SUCCESS):
    execution = MagicMock(spec=MlExecution)
    execution.execution_state = state
    execution.execution_kind = ExecutionKind.API
    execution.token_usage = None
    artifact = MagicMock(spec=Artifact)
    artifact.artifact_type = ArtifactType.STDOUT
    artifact.content = stdout.encode()
    execution.artifacts = [artifact]
    execution.call_identity = MagicMock()
    execution.call_identity.generate_key.return_value = "gateway-key-001"
    return execution


def _patched_client(tmp_path: Path, execution) -> TestClient:
    from generic_ml_cache_daemon.app import create_app

    app = create_app(tmp_path)
    app.state.wired.run_ml.execute = MagicMock(return_value=execution)
    return TestClient(app)


_SINGLE_TURN = {
    "model": "claude-opus-4-8",
    "messages": [{"role": "user", "content": "Hello!"}],
}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_gateway_returns_200(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    response = tc.post(_URL, json=_SINGLE_TURN)
    assert response.status_code == 200


def test_gateway_returns_content_block(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution(stdout="World!"))
    body = tc.post(_URL, json=_SINGLE_TURN).json()
    assert body["content"][0]["type"] == "text"
    assert body["content"][0]["text"] == "World!"


def test_gateway_returns_role_assistant(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    body = tc.post(_URL, json=_SINGLE_TURN).json()
    assert body["role"] == "assistant"


def test_gateway_returns_model_echoed(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    body = tc.post(_URL, json=_SINGLE_TURN).json()
    assert body["model"] == "claude-opus-4-8"


def test_gateway_returns_message_id(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    body = tc.post(_URL, json=_SINGLE_TURN).json()
    assert body["id"].startswith("msg_")


def test_gateway_returns_usage_dict(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    body = tc.post(_URL, json=_SINGLE_TURN).json()
    assert "input_tokens" in body["usage"]
    assert "output_tokens" in body["usage"]


def test_gateway_x_cache_hit_true_on_success(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    body = tc.post(_URL, json=_SINGLE_TURN).json()
    assert body["x_cache_hit"] is True


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_gateway_multi_turn_returns_422(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    multi_turn = {
        "model": "claude-opus-4-8",
        "messages": [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "How are you?"},
        ],
    }
    response = tc.post(_URL, json=multi_turn)
    assert response.status_code == 422


def test_gateway_failed_execution_returns_502(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution(state=ExecutionState.FAILED))
    response = tc.post(_URL, json=_SINGLE_TURN)
    assert response.status_code == 502


def test_gateway_missing_model_returns_422(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    response = tc.post(_URL, json={"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 422


def test_gateway_system_prompt_forwarded(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_execution())
    body = {**_SINGLE_TURN, "system": "You are a helpful assistant."}
    response = tc.post(_URL, json=body)
    assert response.status_code == 200
    call_args = tc.app.state.wired.run_ml.execute.call_args[0][0]
    assert call_args.user_system_prompt == "You are a helpful assistant."


def test_gateway_no_stdout_artifact_returns_empty_content(tmp_path: Path) -> None:
    execution = _make_execution()
    execution.artifacts = []  # no artifacts
    tc = _patched_client(tmp_path, execution)
    body = tc.post(_URL, json=_SINGLE_TURN).json()
    assert body["content"][0]["text"] == ""


def test_gateway_token_usage_present_in_response(tmp_path: Path) -> None:
    execution = _make_execution()
    token_usage = MagicMock()
    token_usage.input_tokens = 10
    token_usage.output_tokens = 20
    execution.token_usage = token_usage
    tc = _patched_client(tmp_path, execution)
    body = tc.post(_URL, json=_SINGLE_TURN).json()
    assert body["usage"]["input_tokens"] == 10
    assert body["usage"]["output_tokens"] == 20
