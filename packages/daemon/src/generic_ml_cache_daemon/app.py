# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory for the generic-ml-cache daemon."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from generic_ml_cache_bootstrap.application import build_application_api
from generic_ml_cache_bootstrap.diagnostics import build_diagnostics
from generic_ml_cache_bootstrap.persistence_backend import sqlite_persistence_backend
from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.application.port.outbound.registered_adapter_port import (
    RegisteredAdapterPort,
)
from generic_ml_cache_core.common.errors import CacheError

from generic_ml_cache_daemon import __version__
from generic_ml_cache_daemon.scheduler import EvictionScheduler, EvictionStats

_DB_NAME = "executions.sqlite3"

_CACHE_ERROR_HTTP: dict[str, int] = {
    "cache.miss": 404,
    "adapter.unknown": 400,
    "adapter.not_found": 400,
    "adapter.command_too_long": 400,
    "config.invalid": 422,
    "input.file_error": 422,
    "store.blob_missing": 404,
    "crypto.wrong_token": 401,
    "crypto.token_required": 401,
    "crypto.state_error": 409,
    "store.locked": 409,
    "store.unavailable": 503,  # DB hard outage — fail loud, never pass through (S2b)
    "provider.api_error": 502,  # upstream provider returned an error (V28)
}
_LOG_FILE_NAME = "gmlcache.log"


async def _cache_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map a :class:`CacheError` to its HTTP status. Registered only for
    ``CacheError``, so ``exc`` is always one; the ``Exception`` parameter type is
    the signature Starlette's handler registry requires."""
    code = exc.code if isinstance(exc, CacheError) else "internal_error"
    status = _CACHE_ERROR_HTTP.get(code, 500)
    return JSONResponse(status_code=status, content={"code": code, "detail": str(exc)})


_CAPTURE_ENV_FLAG = "GMLCACHE_GATEWAY_CAPTURE"
_CAPTURE_ENV_PATH = "GMLCACHE_GATEWAY_CAPTURE_PATH"
_CAPTURE_FILENAME = "gateway-capture.ndjson"


def _resolve_capture_path(store_root: Path) -> Path | None:
    """Return the capture file path when capture is enabled, else None."""
    if not os.environ.get(_CAPTURE_ENV_FLAG):
        return None
    custom_path = os.environ.get(_CAPTURE_ENV_PATH)
    if custom_path:
        return Path(custom_path)
    return store_root / _CAPTURE_FILENAME


def create_app(
    store_root: Path,
    *,
    session_id: str | None = None,
    enable_metrics: bool = False,
    max_size: int | None = None,
    max_age: float | None = None,
    eviction_interval: float = 3600.0,
    whitelist: frozenset[str] | None = None,
) -> FastAPI:
    """Create and configure the daemon FastAPI application.

    Args:
        store_root: path to the gmlcache store directory (the injected data source).
        session_id: optional session all intercepted calls are recorded under.
        enable_metrics: expose the Prometheus /metrics endpoint.
        max_size: optional store size cap in bytes; eviction runs each interval.
        max_age: optional max seconds since last access; stale entries evicted each interval.
        eviction_interval: seconds between eviction sweeps (default 3600).

    Returns:
        A fully wired FastAPI application. Routes are mounted by this function;
        callers should not mount additional routes after construction.
    """
    log_level = os.environ.get("GMLCACHE_LOG_LEVEL")
    log_file_env = os.environ.get("GMLCACHE_LOG_FILE")
    log_file = None
    if log_level:
        log_file = Path(log_file_env) if log_file_env else store_root / _LOG_FILE_NAME
    _diag = build_diagnostics(log_level, log_file)
    # The daemon shares its persistence connection across an async thread pool, so it
    # injects a SQLite backend built with check_same_thread=False (the CLI uses the
    # default single-threaded backend). Everything else defaults.
    _persistence = sqlite_persistence_backend(store_root / _DB_NAME, _diag, check_same_thread=False)
    _encryption_token = os.environ.get("GMLCACHE_TOKEN") or None

    # The daemon wires every whitelisted client (the CLI wires one selected
    # client). The service selects by command.client and dispatches by kind: a
    # CLI adapter answers managed; an API adapter answers API — passthrough is
    # not exposed over REST. An unknown/non-whitelisted client is rejected at
    # /run before it reaches the service.
    def _runners(
        catalog: AdapterCatalogPort, resolver: AdapterResolverPort
    ) -> dict[str, RegisteredAdapterPort]:
        runners: dict[str, RegisteredAdapterPort] = {}
        for descriptor in catalog.list_adapters():
            if descriptor.boundary is AdapterBoundary.API:
                runners[descriptor.client_name] = cast(
                    RegisteredAdapterPort, resolver.resolve_runner(descriptor.adapter_id)
                )
            else:
                runners[descriptor.client_name] = cast(
                    RegisteredAdapterPort, resolver.resolve_local_client(descriptor.adapter_id)
                )
        return runners

    wired_use_cases = build_application_api(
        store_root,
        _runners,
        persistence=_persistence,
        encryption_token=_encryption_token,
        max_size=max_size,
        whitelist=whitelist,
        diag=_diag,
    )

    eviction_stats = EvictionStats(
        max_size=max_size,
        max_age=max_age,
        interval=eviction_interval,
    )
    scheduler = EvictionScheduler(
        wired_use_cases.evict_to_quota,
        wired_use_cases.evict_stale,
        eviction_stats,
        interval=eviction_interval,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if max_size is not None or max_age is not None:
            scheduler.start()
        try:
            yield
        finally:
            await scheduler.stop()

    application = FastAPI(
        title="generic-ml-cache daemon",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    application.add_exception_handler(CacheError, _cache_error_handler)

    application.state.wired = wired_use_cases
    application.state.store_root = store_root
    application.state.session_id = session_id
    application.state.enable_metrics = enable_metrics
    application.state.eviction_stats = eviction_stats
    application.state.whitelist = whitelist

    from generic_ml_cache_daemon.controllers.executions import router as executions_router
    from generic_ml_cache_daemon.controllers.gateway import router as gateway_router
    from generic_ml_cache_daemon.controllers.health import router as health_router
    from generic_ml_cache_daemon.controllers.jobs import router as jobs_router
    from generic_ml_cache_daemon.controllers.run import router as run_router
    from generic_ml_cache_daemon.controllers.sessions import router as sessions_router
    from generic_ml_cache_daemon.jobs import JobRegistry

    application.state.job_registry = JobRegistry()
    application.include_router(health_router)
    application.include_router(sessions_router)
    application.include_router(executions_router)
    application.include_router(run_router)
    application.include_router(jobs_router)
    application.include_router(gateway_router)

    capture_path = _resolve_capture_path(store_root)
    if capture_path is not None:
        from generic_ml_cache_daemon.infrastructure.capture import GatewayCaptureMiddleware

        application.add_middleware(GatewayCaptureMiddleware, capture_path=capture_path)

    return application
