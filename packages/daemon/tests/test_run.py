# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for POST /run."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import (
    ExecutionState,
)
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from starlette.testclient import TestClient


def _make_mock_execution(
    stdout: str = "hello",
    state: ExecutionState = ExecutionState.SUCCESS,
) -> MlExecution:
    """Build a minimal MlExecution stub with a STDOUT artifact."""
    execution = MagicMock(spec=MlExecution)
    execution.execution_state = state
    execution.execution_kind = ExecutionKind.API
    artifact = MagicMock(spec=Artifact)
    artifact.artifact_type = ArtifactType.STDOUT
    artifact.content = stdout.encode()
    execution.artifacts = [artifact]
    execution.call_identity = MagicMock()
    execution.call_identity.generate_key.return_value = "deadbeef01234567"
    return execution


def _patched_client(tmp_path: Path, execution: MlExecution) -> TestClient:
    from generic_ml_cache_daemon.app import create_app

    app = create_app(tmp_path)
    app.state.wired.run_ml.execute = MagicMock(return_value=execution)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Sync JSON path
# ---------------------------------------------------------------------------


def test_run_unknown_client_returns_400(client: TestClient) -> None:
    body = {"client": "unknown_client_xyz", "model": "m", "prompt": "hi"}
    response = client.post("/run", json=body)
    assert response.status_code == 400


def test_run_unknown_client_detail_mentions_client(client: TestClient) -> None:
    body = {"client": "unknown_client_xyz", "model": "m", "prompt": "hi"}
    detail = client.post("/run", json=body).json()["detail"]
    assert "unknown_client_xyz" in detail


def test_run_sync_returns_200(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_mock_execution()) as tc:
        response = tc.post("/run", json={"client": "anthropic", "model": "m", "prompt": "hi"})
    assert response.status_code == 200


def test_run_sync_returns_execution_key(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_mock_execution()) as tc:
        body = tc.post("/run", json={"client": "anthropic", "model": "m"}).json()
    assert body["execution_key"] == "deadbeef01234567"


def test_run_sync_returns_state(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_mock_execution()) as tc:
        body = tc.post("/run", json={"client": "anthropic", "model": "m"}).json()
    assert body["state"] == "success"


def test_run_sync_returns_stdout(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_mock_execution(stdout="world")) as tc:
        body = tc.post("/run", json={"client": "anthropic", "model": "m"}).json()
    assert body["stdout"] == "world"


def test_run_sync_cache_hit_flag_true_when_success_with_stdout(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_mock_execution()) as tc:
        body = tc.post("/run", json={"client": "anthropic", "model": "m"}).json()
    assert body["cache_hit"] is True


def test_run_sync_no_stdout_returns_none(tmp_path: Path) -> None:
    execution = _make_mock_execution()
    execution.artifacts = []
    with _patched_client(tmp_path, execution) as tc:
        body = tc.post("/run", json={"client": "anthropic", "model": "m"}).json()
    assert body["stdout"] is None


# ---------------------------------------------------------------------------
# SSE path
# ---------------------------------------------------------------------------


def test_run_sse_returns_event_stream_content_type(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_mock_execution()) as tc:
        with tc.stream(
            "POST",
            "/run",
            json={"client": "anthropic", "model": "m"},
            headers={"Accept": "text/event-stream"},
        ) as response:
            assert "text/event-stream" in response.headers["content-type"]


def test_run_sse_emits_accepted_then_complete(tmp_path: Path) -> None:
    with _patched_client(tmp_path, _make_mock_execution(stdout="sse-out")) as tc:
        with tc.stream(
            "POST",
            "/run",
            json={"client": "anthropic", "model": "m"},
            headers={"Accept": "text/event-stream"},
        ) as response:
            lines = [ln for ln in response.iter_lines() if ln.startswith("data:")]
    assert len(lines) >= 2
    accepted = json.loads(lines[0].removeprefix("data: "))
    assert accepted["type"] == "accepted"
    complete = json.loads(lines[1].removeprefix("data: "))
    assert complete["type"] == "complete"
    assert complete["stdout"] == "sse-out"


@pytest.mark.parametrize(
    "missing_field",
    ["client", "model"],
)
def test_run_missing_required_field_returns_422(client: TestClient, missing_field: str) -> None:
    body = {"client": "anthropic", "model": "m", "prompt": "x"}
    del body[missing_field]
    response = client.post("/run", json=body)
    assert response.status_code == 422
