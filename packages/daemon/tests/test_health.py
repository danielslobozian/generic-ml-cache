# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for /health, /ready, /info, and /metrics endpoints."""

from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_200(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body_status_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# /ready
# ---------------------------------------------------------------------------


def test_ready_returns_200_for_accessible_store(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200


def test_ready_body_status_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.json()["status"] == "ready"


def test_ready_returns_503_when_store_inaccessible(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from generic_ml_cache_daemon.app import create_app

    application = create_app(tmp_path)
    application.state.wired.metrics.event_counts = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("simulated store failure")
    )

    test_client = TestClient(application, raise_server_exceptions=False)
    response = test_client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not ready"


# ---------------------------------------------------------------------------
# /info
# ---------------------------------------------------------------------------


def test_info_returns_200(client: TestClient) -> None:
    response = client.get("/info")
    assert response.status_code == 200


def test_info_includes_version(client: TestClient) -> None:
    from generic_ml_cache_daemon import __version__

    response = client.get("/info")
    assert response.json()["version"] == __version__


def test_info_includes_store_root(client: TestClient, tmp_path: Path) -> None:
    response = client.get("/info")
    assert response.json()["store_root"] == str(tmp_path)


def test_info_session_id_none_by_default(client: TestClient) -> None:
    response = client.get("/info")
    assert response.json()["session_id"] is None


def test_info_session_id_returned_when_bound(tmp_path: Path) -> None:
    from generic_ml_cache_daemon.app import create_app

    application = create_app(tmp_path, session_id="my-session")
    test_client = TestClient(application)
    response = test_client.get("/info")
    assert response.json()["session_id"] == "my-session"


def test_info_adapters_is_non_empty_list(client: TestClient) -> None:
    adapters = client.get("/info").json()["adapters"]
    assert isinstance(adapters, list)
    assert len(adapters) > 0


def test_info_adapters_sorted(client: TestClient) -> None:
    adapters = client.get("/info").json()["adapters"]
    assert adapters == sorted(adapters)


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------


def test_metrics_returns_503_when_not_enabled(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 503


def test_metrics_returns_503_detail_mentions_enabled(client: TestClient) -> None:
    response = client.get("/metrics")
    assert "not enabled" in response.json()["detail"]


def test_metrics_returns_200_when_enabled(tmp_path: Path) -> None:
    from generic_ml_cache_daemon.app import create_app

    application = create_app(tmp_path, enable_metrics=True)
    test_client = TestClient(application)
    response = test_client.get("/metrics")
    assert response.status_code == 200


def test_metrics_returns_prometheus_text_when_enabled(tmp_path: Path) -> None:
    from generic_ml_cache_daemon.app import create_app

    application = create_app(tmp_path, enable_metrics=True)
    test_client = TestClient(application)
    response = test_client.get("/metrics")
    assert "python_gc_objects_collected_total" in response.text
