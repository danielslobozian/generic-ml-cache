# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Routes: /health, /ready, /info, /metrics."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from generic_ml_cache_core.adapter.out.api.api_registry import registered_api_names
from generic_ml_cache_core.adapter.out.client.registry import registered_names

from generic_ml_cache_daemon import __version__
from generic_ml_cache_daemon.metrics import is_prometheus_available
from generic_ml_cache_daemon.models.health import (
    EvictionInfo,
    HealthResponse,
    InfoResponse,
    ReadyResponse,
)

router = APIRouter()


@router.get("/health")
def get_health() -> HealthResponse:
    """Liveness: confirm the daemon process is alive."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
def get_ready(request: Request) -> Response:
    """Readiness: confirm the store is accessible and the daemon can serve requests."""
    wired = request.app.state.wired
    try:
        wired.metrics.event_counts()
        return JSONResponse(content=ReadyResponse(status="ready").model_dump())
    except Exception:
        return JSONResponse(
            status_code=503,
            content=ReadyResponse(status="not ready", detail="store not accessible").model_dump(),
        )


@router.get("/info", response_model=InfoResponse)
def get_info(request: Request) -> InfoResponse:
    """Return daemon version, store path, active adapters, and bound session."""
    store_root: str = str(request.app.state.store_root)
    session_id: str | None = request.app.state.session_id
    all_adapter_names: List[str] = sorted(set(registered_names()) | set(registered_api_names()))
    stats = request.app.state.eviction_stats
    return InfoResponse(
        version=__version__,
        store_root=store_root,
        session_id=session_id,
        adapters=all_adapter_names,
        eviction=EvictionInfo(
            max_size=stats.max_size,
            max_age=stats.max_age,
            interval=stats.interval,
            last_run_at=stats.last_run_at,
            last_executions_removed=stats.last_executions_removed,
            last_bytes_freed=stats.last_bytes_freed,
        ),
    )


@router.get("/metrics")
def get_metrics(request: Request) -> Response:
    """Prometheus metrics. Requires the [metrics] extra and enable_metrics=True."""
    if not request.app.state.enable_metrics:
        return JSONResponse(
            status_code=503,
            content={"detail": "metrics endpoint not enabled (start daemon with --metrics)"},
        )
    if not is_prometheus_available():  # pragma: no cover
        return JSONResponse(
            status_code=501,
            content={"detail": "prometheus-client extra not installed"},
        )
    import prometheus_client  # type: ignore[import-untyped]

    metrics_output = prometheus_client.generate_latest()
    return PlainTextResponse(
        content=metrics_output.decode("utf-8"),
        media_type=prometheus_client.CONTENT_TYPE_LATEST,
    )
