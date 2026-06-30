# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the /sessions HTTP API."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# GET /sessions — list
# ---------------------------------------------------------------------------


def test_list_sessions_empty_store(client: TestClient) -> None:
    response = client.get("/sessions")
    assert response.status_code == 200
    assert response.json()["session_ids"] == []


def test_list_sessions_returns_created_session(client: TestClient) -> None:
    r = client.post("/sessions", json={"tags": ["list-test"]})
    session_id = r.json()["session_id"]
    ids = client.get("/sessions").json()["session_ids"]
    assert session_id in ids


# ---------------------------------------------------------------------------
# POST /sessions — create
# ---------------------------------------------------------------------------


def test_create_session_returns_201(client: TestClient) -> None:
    response = client.post("/sessions", json={})
    assert response.status_code == 201


def test_create_session_returns_session_id(client: TestClient) -> None:
    response = client.post("/sessions", json={})
    assert "session_id" in response.json()
    assert len(response.json()["session_id"]) == 16  # token_hex(8)


def test_create_session_empty_tags_by_default(client: TestClient) -> None:
    response = client.post("/sessions", json={})
    assert response.json()["tags"] == []


def test_create_session_no_spec_by_default(client: TestClient) -> None:
    response = client.post("/sessions", json={})
    assert response.json()["spec"] is None


def test_create_session_with_tags(client: TestClient) -> None:
    response = client.post("/sessions", json={"tags": ["TICKET-1", "v2"]})
    assert set(response.json()["tags"]) == {"TICKET-1", "v2"}


def test_create_session_with_spec(client: TestClient) -> None:
    body = {"spec": {"client": "claude", "model": "claude-opus-4-8", "effort": "medium"}}
    response = client.post("/sessions", json=body)
    spec = response.json()["spec"]
    assert spec["client"] == "claude"
    assert spec["model"] == "claude-opus-4-8"
    assert spec["effort"] == "medium"


def test_create_session_ids_are_unique(client: TestClient) -> None:
    ids = {client.post("/sessions", json={}).json()["session_id"] for _ in range(5)}
    assert len(ids) == 5


# ---------------------------------------------------------------------------
# GET /sessions/{id} — get
# ---------------------------------------------------------------------------


def test_get_session_returns_200_for_existing(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"tags": ["x"]}).json()["session_id"]
    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 200


def test_get_session_returns_404_for_unknown(client: TestClient) -> None:
    response = client.get("/sessions/nonexistent-session-id")
    assert response.status_code == 404


def test_get_session_returns_correct_tags(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"tags": ["alpha"]}).json()["session_id"]
    tags = client.get(f"/sessions/{session_id}").json()["tags"]
    assert "alpha" in tags


# ---------------------------------------------------------------------------
# GET /sessions/{id}/stats — stats
# ---------------------------------------------------------------------------


def test_get_stats_returns_200_for_new_session(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    response = client.get(f"/sessions/{session_id}/stats")
    assert response.status_code == 200


def test_get_stats_calls_zero_for_new_session(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    stats = client.get(f"/sessions/{session_id}/stats").json()
    assert stats["calls"] == 0
    assert stats["hits"] == 0
    assert stats["hit_rate"] == 0.0


def test_get_stats_by_model_empty_for_new_session(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    stats = client.get(f"/sessions/{session_id}/stats").json()
    assert stats["by_model"] == []


def _seed_metrics(tmp_path):
    """Build the metrics out-port directly to seed journal events — it is no
    longer exposed on the narrowed ApplicationApi (controllers go through ports)."""
    import sqlite3

    from generic_ml_cache_adapters.adapter.out.metrics.access_registry import AccessRegistry
    from generic_ml_cache_adapters.adapter.out.metrics.journal_metrics import JournalMetrics

    def _factory():
        return sqlite3.connect(str(tmp_path / "executions.sqlite3"), check_same_thread=False)

    return JournalMetrics(AccessRegistry(_factory))


def test_get_stats_by_model_present_after_events(app_and_client, tmp_path) -> None:
    _application, http_client = app_and_client
    metrics = _seed_metrics(tmp_path)
    session_id = http_client.post("/sessions", json={}).json()["session_id"]

    metrics.record_event(
        "record",
        execution_key="k1",
        client="claude",
        model="sonnet",
        effort="high",
        session_id=session_id,
    )
    metrics.record_event(
        "hit",
        execution_key="k1",
        client="claude",
        model="sonnet",
        effort="high",
        session_id=session_id,
    )

    stats = http_client.get(f"/sessions/{session_id}/stats").json()
    assert stats["calls"] == 2
    assert stats["hits"] == 1
    assert len(stats["by_model"]) == 1
    model_row = stats["by_model"][0]
    assert model_row["client"] == "claude"
    assert model_row["model"] == "sonnet"
    assert model_row["executions"] == 1
    assert model_row["hits"] == 1


def test_get_stats_by_model_token_fields_present(app_and_client, tmp_path) -> None:
    _application, http_client = app_and_client
    metrics = _seed_metrics(tmp_path)
    session_id = http_client.post("/sessions", json={}).json()["session_id"]
    metrics.record_event(
        "record",
        execution_key="k9",
        client="openai",
        model="gpt-4o",
        effort="",
        session_id=session_id,
    )

    stats = http_client.get(f"/sessions/{session_id}/stats").json()
    model_row = stats["by_model"][0]
    for token_field in (
        "spent_input",
        "spent_output",
        "cache_read_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "saved_tokens",
    ):
        assert token_field in model_row, f"missing field: {token_field}"


# ---------------------------------------------------------------------------
# PUT /sessions/{id}/spec — set spec
# ---------------------------------------------------------------------------


def test_set_spec_returns_200(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    body = {"client": "cursor", "model": "gpt-4o", "effort": ""}
    response = client.put(f"/sessions/{session_id}/spec", json=body)
    assert response.status_code == 200


def test_set_spec_persists(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    client.put(
        f"/sessions/{session_id}/spec",
        json={"client": "claude", "model": "claude-opus-4-8", "effort": "high"},
    )
    spec = client.get(f"/sessions/{session_id}").json()["spec"]
    assert spec["model"] == "claude-opus-4-8"


def test_set_spec_replaces_previous(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    client.put(f"/sessions/{session_id}/spec", json={"client": "a", "model": "m1", "effort": ""})
    client.put(f"/sessions/{session_id}/spec", json={"client": "b", "model": "m2", "effort": ""})
    spec = client.get(f"/sessions/{session_id}").json()["spec"]
    assert spec["client"] == "b"


# ---------------------------------------------------------------------------
# DELETE /sessions/{id}/spec — clear spec
# ---------------------------------------------------------------------------


def test_clear_spec_returns_204(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    client.put(f"/sessions/{session_id}/spec", json={"client": "a", "model": "m", "effort": ""})
    response = client.delete(f"/sessions/{session_id}/spec")
    assert response.status_code == 204


def test_clear_spec_removes_spec(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"tags": ["t"]}).json()["session_id"]
    client.put(f"/sessions/{session_id}/spec", json={"client": "a", "model": "m", "effort": ""})
    client.delete(f"/sessions/{session_id}/spec")
    spec = client.get(f"/sessions/{session_id}").json()["spec"]
    assert spec is None


def test_clear_spec_noop_when_absent(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"tags": ["t"]}).json()["session_id"]
    response = client.delete(f"/sessions/{session_id}/spec")
    assert response.status_code == 204


# ---------------------------------------------------------------------------
# POST /sessions/{id}/tags — add tag
# ---------------------------------------------------------------------------


def test_add_tag_returns_201(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    response = client.post(f"/sessions/{session_id}/tags", json={"tag": "newt"})
    assert response.status_code == 201


def test_add_tag_appears_in_session(client: TestClient) -> None:
    session_id = client.post("/sessions", json={}).json()["session_id"]
    client.post(f"/sessions/{session_id}/tags", json={"tag": "RELEASE"})
    tags = client.get(f"/sessions/{session_id}").json()["tags"]
    assert "RELEASE" in tags


# ---------------------------------------------------------------------------
# DELETE /sessions/{id}/tags/{tag} — remove tag
# ---------------------------------------------------------------------------


def test_remove_tag_returns_204(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"tags": ["removeme"]}).json()["session_id"]
    response = client.delete(f"/sessions/{session_id}/tags/removeme")
    assert response.status_code == 204


def test_remove_tag_detaches_it(client: TestClient) -> None:
    session_id = client.post("/sessions", json={"tags": ["gone", "keep"]}).json()["session_id"]
    client.delete(f"/sessions/{session_id}/tags/gone")
    tags = client.get(f"/sessions/{session_id}").json()["tags"]
    assert "gone" not in tags
    assert "keep" in tags


def test_remove_tag_noop_when_absent(tmp_path: Path) -> None:
    from generic_ml_cache_daemon.app import create_app

    application = create_app(tmp_path)
    with TestClient(application) as test_client:
        session_id = test_client.post("/sessions", json={"tags": ["x"]}).json()["session_id"]
        response = test_client.delete(f"/sessions/{session_id}/tags/notthere")
    assert response.status_code == 204
