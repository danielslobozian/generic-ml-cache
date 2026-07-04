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
    application.state.wired.event_counts.event_counts = MagicMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("simulated store failure")
    )

    with TestClient(application, raise_server_exceptions=False) as test_client:
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
    with TestClient(application) as test_client:
        response = test_client.get("/info")
    assert response.json()["session_id"] == "my-session"


def test_info_adapters_is_non_empty_list(client: TestClient) -> None:
    adapters = client.get("/info").json()["adapters"]
    assert isinstance(adapters, list)
    assert len(adapters) > 0


def test_info_adapters_sorted(client: TestClient) -> None:
    adapters = client.get("/info").json()["adapters"]
    assert adapters == sorted(adapters)


def test_info_adapters_lists_bundled_adapters_despite_whitelist(tmp_path: Path) -> None:
    # G1: the bundled adapters always load; the whitelist gates only third-party
    # entry-point plugins, so a whitelist that names none of them hides nothing.
    from generic_ml_cache_daemon.app import create_app

    application = create_app(tmp_path, whitelist=frozenset({"fake", "fake_stdin"}))
    with TestClient(application) as test_client:
        adapters = test_client.get("/info").json()["adapters"]
    assert "claude" in adapters
    assert len(adapters) >= 6  # the six bundled clients


def test_info_adapters_none_whitelist_returns_all(client: TestClient) -> None:
    no_filter = client.get("/info").json()["adapters"]
    assert len(no_filter) >= 1


def test_info_adapters_unknown_whitelist_name_does_not_hide_builtins(tmp_path: Path) -> None:
    # An unknown whitelist entry gates no third-party plugin and hides no
    # bundled/registered adapter — the safe-default set is still present.
    from generic_ml_cache_daemon.app import create_app

    application = create_app(tmp_path, whitelist=frozenset({"__nonexistent__"}))
    with TestClient(application) as test_client:
        adapters = test_client.get("/info").json()["adapters"]
    assert adapters != []


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
    with TestClient(application) as test_client:
        response = test_client.get("/metrics")
    assert response.status_code == 200


def test_metrics_returns_prometheus_text_when_enabled(tmp_path: Path) -> None:
    from generic_ml_cache_daemon.app import create_app

    application = create_app(tmp_path, enable_metrics=True)
    with TestClient(application) as test_client:
        response = test_client.get("/metrics")
    assert "python_gc_objects_collected_total" in response.text
