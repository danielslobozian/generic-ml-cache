# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for GatewayCaptureMiddleware."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from generic_ml_cache_daemon.middleware.capture import GatewayCaptureMiddleware


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(capture_path: Path) -> FastAPI:
    application = FastAPI()
    application.add_middleware(GatewayCaptureMiddleware, capture_path=capture_path)

    @application.post("/gateway/claude/v1/messages")
    def mock_gateway(request_body: dict):
        return JSONResponse({"role": "assistant", "content": "hello"})

    @application.get("/health")
    def health():
        return JSONResponse({"status": "ok"})

    return application


def _read_records(capture_path: Path) -> list[dict]:
    if not capture_path.exists():
        return []
    return [json.loads(line) for line in capture_path.read_text().splitlines() if line]


# ---------------------------------------------------------------------------
# Non-gateway paths
# ---------------------------------------------------------------------------


def test_non_gateway_path_is_not_captured(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.get("/health")

    assert _read_records(capture_path) == []


# ---------------------------------------------------------------------------
# Gateway paths are captured
# ---------------------------------------------------------------------------


def test_gateway_request_produces_one_record(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post("/gateway/claude/v1/messages", json={"model": "claude-opus-4-8"})

    assert len(_read_records(capture_path)) == 1


def test_captured_record_has_all_expected_fields(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post("/gateway/claude/v1/messages", json={"model": "claude-opus-4-8"})
    record = _read_records(capture_path)[0]

    for field in (
        "ts",
        "method",
        "path",
        "request_headers",
        "request_body",
        "response_status",
        "response_body",
        "duration_ms",
    ):
        assert field in record, f"missing field: {field}"


def test_captured_record_method_and_path(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post("/gateway/claude/v1/messages", json={"model": "m"})
    record = _read_records(capture_path)[0]

    assert record["method"] == "POST"
    assert record["path"] == "/gateway/claude/v1/messages"


def test_captured_request_body_is_parsed_json(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post("/gateway/claude/v1/messages", json={"model": "sonnet", "x": 1})
    record = _read_records(capture_path)[0]

    assert record["request_body"] == {"model": "sonnet", "x": 1}


def test_captured_response_body_is_parsed_json(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post("/gateway/claude/v1/messages", json={"model": "m"})
    record = _read_records(capture_path)[0]

    assert record["response_body"]["role"] == "assistant"
    assert record["response_status"] == 200


def test_captured_duration_ms_is_non_negative(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post("/gateway/claude/v1/messages", json={"model": "m"})
    record = _read_records(capture_path)[0]

    assert isinstance(record["duration_ms"], int)
    assert record["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# Header redaction
# ---------------------------------------------------------------------------


def test_x_api_key_header_is_redacted(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post(
        "/gateway/claude/v1/messages",
        json={"model": "m"},
        headers={"x-api-key": "sk-secret-value"},
    )
    record = _read_records(capture_path)[0]

    assert record["request_headers"].get("x-api-key") == "[REDACTED]"


def test_authorization_header_is_redacted(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post(
        "/gateway/claude/v1/messages",
        json={"model": "m"},
        headers={"Authorization": "Bearer tok123"},
    )
    record = _read_records(capture_path)[0]

    assert record["request_headers"].get("authorization") == "[REDACTED]"


def test_chatgpt_account_id_header_is_redacted(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post(
        "/gateway/claude/v1/messages",
        json={"model": "m"},
        headers={"chatgpt-account-id": "workspace-secret"},
    )
    record = _read_records(capture_path)[0]

    assert record["request_headers"].get("chatgpt-account-id") == "[REDACTED]"


def test_non_sensitive_headers_are_preserved(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post(
        "/gateway/claude/v1/messages",
        json={"model": "m"},
        headers={"anthropic-version": "2023-06-01"},
    )
    record = _read_records(capture_path)[0]

    assert record["request_headers"].get("anthropic-version") == "2023-06-01"


# ---------------------------------------------------------------------------
# NDJSON — multiple requests append, one record per line
# ---------------------------------------------------------------------------


def test_multiple_requests_produce_multiple_records(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post("/gateway/claude/v1/messages", json={"model": "a"})
    test_client.post("/gateway/claude/v1/messages", json={"model": "b"})
    test_client.post("/gateway/claude/v1/messages", json={"model": "c"})

    records = _read_records(capture_path)
    assert len(records) == 3
    assert records[0]["request_body"]["model"] == "a"
    assert records[2]["request_body"]["model"] == "c"


# ---------------------------------------------------------------------------
# Non-JSON bodies are captured as strings
# ---------------------------------------------------------------------------


def test_non_json_request_body_captured_as_string(tmp_path: Path) -> None:
    capture_path = tmp_path / "capture.ndjson"
    test_client = TestClient(_make_app(capture_path))

    test_client.post(
        "/gateway/claude/v1/messages",
        content=b"not json at all",
        headers={"content-type": "text/plain"},
    )
    record = _read_records(capture_path)[0]

    assert isinstance(record["request_body"], str)
    assert "not json" in record["request_body"]


# ---------------------------------------------------------------------------
# app.py wiring — GMLCACHE_GATEWAY_CAPTURE env var
# ---------------------------------------------------------------------------


def test_capture_disabled_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GMLCACHE_GATEWAY_CAPTURE", raising=False)

    from generic_ml_cache_daemon.app import _resolve_capture_path

    assert _resolve_capture_path(tmp_path) is None


def test_capture_enabled_by_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GMLCACHE_GATEWAY_CAPTURE", "1")

    from generic_ml_cache_daemon.app import _resolve_capture_path

    capture_path = _resolve_capture_path(tmp_path)
    assert capture_path is not None
    assert capture_path == tmp_path / "gateway-capture.ndjson"


def test_capture_path_overridden_by_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom_path = str(tmp_path / "custom" / "out.ndjson")
    monkeypatch.setenv("GMLCACHE_GATEWAY_CAPTURE", "1")
    monkeypatch.setenv("GMLCACHE_GATEWAY_CAPTURE_PATH", custom_path)

    from generic_ml_cache_daemon.app import _resolve_capture_path

    assert _resolve_capture_path(tmp_path) == Path(custom_path)
