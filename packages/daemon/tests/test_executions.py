# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for /executions, /stats, and /purge endpoints."""

from __future__ import annotations

from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# GET /executions — list
# ---------------------------------------------------------------------------


def test_list_executions_returns_200(client: TestClient) -> None:
    response = client.get("/executions")
    assert response.status_code == 200


def test_list_executions_empty_store(client: TestClient) -> None:
    body = client.get("/executions").json()
    assert body["executions"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# GET /executions/{key} — inspect
# ---------------------------------------------------------------------------


def test_get_execution_returns_404_for_unknown(client: TestClient) -> None:
    response = client.get("/executions/doesnotexist")
    assert response.status_code == 404


def test_get_execution_404_detail_mentions_key(client: TestClient) -> None:
    response = client.get("/executions/missing-key")
    assert "missing-key" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /stats — global stats
# ---------------------------------------------------------------------------


def test_stats_returns_200(client: TestClient) -> None:
    response = client.get("/stats")
    assert response.status_code == 200


def test_stats_executions_zero_for_empty_store(client: TestClient) -> None:
    body = client.get("/stats").json()
    assert body["executions"] == 0


def test_stats_event_counts_is_dict(client: TestClient) -> None:
    body = client.get("/stats").json()
    assert isinstance(body["event_counts"], dict)


# ---------------------------------------------------------------------------
# POST /purge — purge
# ---------------------------------------------------------------------------


def test_purge_all_returns_200(client: TestClient) -> None:
    response = client.post("/purge", json={"by": "all"})
    assert response.status_code == 200


def test_purge_all_empty_store_zeroes(client: TestClient) -> None:
    body = client.post("/purge", json={"by": "all"}).json()
    assert body["executions_removed"] == 0
    assert body["bytes_freed"] == 0
    assert body["blobs_removed"] == 0


def test_purge_by_key_returns_200(client: TestClient) -> None:
    response = client.post("/purge", json={"by": "key", "target": "nokey"})
    assert response.status_code == 200


def test_purge_by_tag_returns_200(client: TestClient) -> None:
    response = client.post("/purge", json={"by": "tag", "target": "notag"})
    assert response.status_code == 200


def test_purge_by_session_returns_200(client: TestClient) -> None:
    response = client.post("/purge", json={"by": "session", "target": "nosession"})
    assert response.status_code == 200


def test_purge_by_session_tag_returns_200(client: TestClient) -> None:
    response = client.post("/purge", json={"by": "session_tag", "target": "notag"})
    assert response.status_code == 200


def test_purge_unknown_discriminator_returns_422(client: TestClient) -> None:
    response = client.post("/purge", json={"by": "unknown_scope", "target": "x"})
    assert response.status_code == 422
