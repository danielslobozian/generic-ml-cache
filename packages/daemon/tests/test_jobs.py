# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the /jobs HTTP API."""

from __future__ import annotations

import json
import time
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


def _make_mock_execution(stdout: str = "job-output") -> MlExecution:
    execution = MagicMock(spec=MlExecution)
    execution.execution_state = ExecutionState.SUCCESS
    execution.execution_kind = ExecutionKind.API
    artifact = MagicMock(spec=Artifact)
    artifact.artifact_type = ArtifactType.STDOUT
    artifact.content = stdout.encode()
    execution.artifacts = [artifact]
    execution.call_identity = MagicMock()
    execution.call_identity.generate_key.return_value = "aabbccdd00112233"
    return execution


def _patched_client(tmp_path: Path, execution: MlExecution) -> TestClient:
    from generic_ml_cache_daemon.app import create_app

    app = create_app(tmp_path)
    app.state.wired.run_ml.execute = MagicMock(return_value=execution)
    return TestClient(app)


# ---------------------------------------------------------------------------
# POST /jobs — submit
# ---------------------------------------------------------------------------


def test_submit_job_returns_202(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    response = tc.post("/jobs", json={"client": "anthropic", "model": "m"})
    assert response.status_code == 202


def test_submit_job_returns_job_id(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    body = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()
    assert "job_id" in body
    assert len(body["job_id"]) == 16


def test_submit_job_initial_state_is_pending_or_running(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    body = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()
    assert body["state"] in ("pending", "running", "done")


def test_submit_job_unknown_client_returns_400(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    response = tc.post("/jobs", json={"client": "nope_xyz", "model": "m"})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /jobs — list
# ---------------------------------------------------------------------------


def test_list_jobs_returns_200(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    response = tc.get("/jobs")
    assert response.status_code == 200


def test_list_jobs_empty_initially(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    body = tc.get("/jobs").json()
    assert body["job_ids"] == []


def test_list_jobs_contains_submitted_job(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    job_id = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()["job_id"]
    job_ids = tc.get("/jobs").json()["job_ids"]
    assert job_id in job_ids


# ---------------------------------------------------------------------------
# GET /jobs/{id} — get status
# ---------------------------------------------------------------------------


def test_get_job_returns_200_for_known(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    job_id = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()["job_id"]
    response = tc.get(f"/jobs/{job_id}")
    assert response.status_code == 200


def test_get_job_returns_404_for_unknown(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    response = tc.get("/jobs/nonexistent")
    assert response.status_code == 404


def test_get_job_eventually_done(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    job_id = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()["job_id"]
    deadline = time.time() + 5.0
    state = None
    while time.time() < deadline:
        state = tc.get(f"/jobs/{job_id}").json()["state"]
        if state == "done":
            break
        time.sleep(0.05)
    assert state == "done"


def test_get_job_done_has_stdout(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution(stdout="final-out"))
    job_id = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()["job_id"]
    deadline = time.time() + 5.0
    while time.time() < deadline:
        body = tc.get(f"/jobs/{job_id}").json()
        if body["state"] == "done":
            assert body["stdout"] == "final-out"
            return
        time.sleep(0.05)
    raise AssertionError("job did not complete in time")


# ---------------------------------------------------------------------------
# GET /jobs/{id}/stream — SSE
# ---------------------------------------------------------------------------


def test_stream_job_returns_event_stream_content_type(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    job_id = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()["job_id"]
    with tc.stream("GET", f"/jobs/{job_id}/stream") as response:
        assert "text/event-stream" in response.headers["content-type"]


def test_stream_job_emits_complete_event(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution(stdout="streamed"))
    job_id = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()["job_id"]
    with tc.stream("GET", f"/jobs/{job_id}/stream") as response:
        lines = [ln for ln in response.iter_lines() if ln.startswith("data:")]
    complete_events = [
        json.loads(ln.removeprefix("data: "))
        for ln in lines
        if json.loads(ln.removeprefix("data: ")).get("type") in ("complete", "error")
    ]
    assert len(complete_events) >= 1
    assert complete_events[-1]["type"] == "complete"


def test_stream_job_404_for_unknown(tmp_path: Path) -> None:
    tc = _patched_client(tmp_path, _make_mock_execution())
    response = tc.get("/jobs/nosuchjob/stream")
    assert response.status_code == 404


def test_stream_job_emits_error_event_on_failure(tmp_path: Path) -> None:
    from generic_ml_cache_daemon.app import create_app

    app = create_app(tmp_path)
    app.state.wired.run_ml.execute = MagicMock(side_effect=RuntimeError("boom"))
    tc = TestClient(app)
    job_id = tc.post("/jobs", json={"client": "anthropic", "model": "m"}).json()["job_id"]
    with tc.stream("GET", f"/jobs/{job_id}/stream") as response:
        lines = [ln for ln in response.iter_lines() if ln.startswith("data:")]
    terminal = [
        json.loads(ln.removeprefix("data: "))
        for ln in lines
        if json.loads(ln.removeprefix("data: ")).get("type") in ("complete", "error")
    ]
    assert terminal[-1]["type"] == "error"
