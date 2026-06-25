# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory for the generic-ml-cache daemon."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from generic_ml_cache_core.adapter.inbound.composition import build_use_cases

from generic_ml_cache_daemon import __version__


def create_app(
    store_root: Path,
    *,
    session_id: Optional[str] = None,
    enable_metrics: bool = False,
) -> FastAPI:
    """Create and configure the daemon FastAPI application.

    Args:
        store_root: path to the gmlcache store directory (the injected data source).
        session_id: optional session all intercepted calls are recorded under.
        enable_metrics: expose the Prometheus /metrics endpoint.

    Returns:
        A fully wired FastAPI application. Routes are mounted by this function;
        callers should not mount additional routes after construction.
    """
    application = FastAPI(
        title="generic-ml-cache daemon",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    wired_use_cases = build_use_cases(store_root)
    application.state.wired = wired_use_cases
    application.state.store_root = store_root
    application.state.session_id = session_id
    application.state.enable_metrics = enable_metrics

    from generic_ml_cache_daemon.routes.executions import router as executions_router
    from generic_ml_cache_daemon.routes.health import router as health_router
    from generic_ml_cache_daemon.routes.sessions import router as sessions_router

    application.include_router(health_router)
    application.include_router(sessions_router)
    application.include_router(executions_router)

    return application
