# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for POST /gateway/claude/{session_id}/v1/messages.

State-based: the real wired daemon runs the whole cache protocol (dispatch → relay →
store → serve); only the relay's upstream HTTP call is stubbed. Assertions are about
observable behaviour — a 200 is cached and served without re-relaying, a failure is
returned verbatim and never cached — not about mock call shapes.
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

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

_SINGLE_TURN = {"model": "claude-opus-4-8", "messages": [{"role": "user", "content": "Hello!"}]}


def _client(tmp_path: Path) -> TestClient:
    from generic_ml_cache_daemon.app import create_app

    return TestClient(create_app(tmp_path))


def _ok_upstream(body: bytes = _ANTHROPIC_BODY, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.__enter__ = lambda self: self
    response.__exit__ = MagicMock(return_value=False)
    response.status = status
    response.read.return_value = body
    return response


# ---------------------------------------------------------------------------
# Miss → relay + cache; hit → serve from the store
# ---------------------------------------------------------------------------


def test_miss_relays_and_returns_the_body_verbatim(tmp_path: Path) -> None:
    with (
        _client(tmp_path) as client,
        patch("urllib.request.urlopen", return_value=_ok_upstream()) as urlopen,
    ):
        response = client.post(_URL, json=_SINGLE_TURN)
    assert response.status_code == 200
    assert response.content == _ANTHROPIC_BODY  # full envelope, not distilled text
    assert urlopen.call_count == 1


def test_second_identical_request_is_served_from_cache_without_re_relaying(tmp_path: Path) -> None:
    with (
        _client(tmp_path) as client,
        patch("urllib.request.urlopen", return_value=_ok_upstream()) as urlopen,
    ):
        first = client.post(_URL, json=_SINGLE_TURN)
        second = client.post(_URL, json=_SINGLE_TURN)
    assert first.content == second.content == _ANTHROPIC_BODY
    assert urlopen.call_count == 1  # the hit served off the finalized record


def test_a_different_body_is_a_separate_cache_entry(tmp_path: Path) -> None:
    other = {"model": "claude-opus-4-8", "messages": [{"role": "user", "content": "Bye"}]}
    with (
        _client(tmp_path) as client,
        patch("urllib.request.urlopen", return_value=_ok_upstream()) as urlopen,
    ):
        client.post(_URL, json=_SINGLE_TURN)
        client.post(_URL, json=other)
    assert urlopen.call_count == 2  # distinct request bodies key distinct entries


# ---------------------------------------------------------------------------
# Upstream error → forwarded verbatim, never cached
# ---------------------------------------------------------------------------


def test_upstream_error_is_forwarded_verbatim_with_its_real_status(tmp_path: Path) -> None:
    error_body = json.dumps({"type": "error", "error": {"type": "rate_limit_error"}}).encode()
    http_error = urllib.error.HTTPError(
        url="https://api.anthropic.com/v1/messages",
        code=429,
        msg="Too Many Requests",
        hdrs=MagicMock(),
        fp=BytesIO(error_body),
    )
    with _client(tmp_path) as client, patch("urllib.request.urlopen", side_effect=http_error):
        response = client.post(_URL, json=_SINGLE_TURN)
    assert response.status_code == 429  # the real upstream status (W15)
    assert response.content == error_body


def test_upstream_error_is_not_cached_and_re_relays(tmp_path: Path) -> None:
    error_body = b'{"type":"error"}'
    http_error = urllib.error.HTTPError(
        url="https://api.anthropic.com/v1/messages",
        code=500,
        msg="Server Error",
        hdrs=MagicMock(),
        fp=BytesIO(error_body),
    )
    with (
        _client(tmp_path) as client,
        patch("urllib.request.urlopen", side_effect=http_error) as urlopen,
    ):
        client.post(_URL, json=_SINGLE_TURN)
        client.post(_URL, json=_SINGLE_TURN)
    assert urlopen.call_count == 2  # a failure is never a servable hit


def test_network_failure_maps_to_502(tmp_path: Path) -> None:
    with (
        _client(tmp_path) as client,
        patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")),
    ):
        response = client.post(_URL, json=_SINGLE_TURN)
    assert response.status_code == 502  # ProviderApiError(status 0) -> daemon 502 (W16)


# ---------------------------------------------------------------------------
# Verbatim forwarding of the request
# ---------------------------------------------------------------------------


def test_forwards_the_request_body_verbatim_upstream(tmp_path: Path) -> None:
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = req.data
        return _ok_upstream()

    body = {**_SINGLE_TURN, "temperature": 0.3, "tools": [{"name": "search"}]}
    with _client(tmp_path) as client, patch("urllib.request.urlopen", fake_urlopen):
        client.post(_URL, json=body)
    # The exact bytes the caller sent are forwarded — no field fabricated or dropped.
    assert json.loads(captured["data"]) == body


def test_forwards_the_caller_auth_header(tmp_path: Path) -> None:
    captured: dict = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = dict(req.headers)
        return _ok_upstream()

    with _client(tmp_path) as client, patch("urllib.request.urlopen", fake_urlopen):
        client.post(_URL, json=_SINGLE_TURN, headers={"authorization": "Bearer sub-tok"})
    assert captured["headers"].get("Authorization") == "Bearer sub-tok"


# ---------------------------------------------------------------------------
# Probe + validation
# ---------------------------------------------------------------------------


def test_probe_endpoint_answers(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get(f"/gateway/claude/{_SESSION}").status_code == 200


def test_missing_model_is_rejected_locally_without_relaying(tmp_path: Path) -> None:
    with _client(tmp_path) as client, patch("urllib.request.urlopen") as urlopen:
        response = client.post(_URL, json={"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 422
    urlopen.assert_not_called()  # rejected before any upstream call


# ---------------------------------------------------------------------------
# _to_http_response: a real upstream status of 0 must not be masked as 502 (Y11 nit)
# ---------------------------------------------------------------------------


def test_upstream_status_zero_is_preserved_not_rewritten_to_502() -> None:
    from types import SimpleNamespace

    from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
        ExecutionFailure,
        FailureReason,
    )
    from generic_ml_cache_core.application.domain.model.execution.execution_state import (
        ExecutionState,
    )

    from generic_ml_cache_daemon.controllers.gateway import _to_http_response

    execution = SimpleNamespace(
        execution_state=ExecutionState.FAILED,
        failure=ExecutionFailure(reason=FailureReason.NONZERO_EXIT, message="x", exit_code=0),
        artifacts=[],
    )
    status, _ = _to_http_response(execution)  # type: ignore[arg-type]
    assert status == 0  # a real 0 is falsy but valid — not silently rewritten to 502


def test_absent_upstream_status_falls_back_to_502() -> None:
    from types import SimpleNamespace

    from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
        ExecutionFailure,
        FailureReason,
    )
    from generic_ml_cache_core.application.domain.model.execution.execution_state import (
        ExecutionState,
    )

    from generic_ml_cache_daemon.controllers.gateway import _to_http_response

    execution = SimpleNamespace(
        execution_state=ExecutionState.FAILED,
        failure=ExecutionFailure(reason=FailureReason.CLIENT_ERROR, message="x", exit_code=None),
        artifacts=[],
    )
    status, _ = _to_http_response(execution)  # type: ignore[arg-type]
    assert status == 502  # a genuinely absent status still falls back
