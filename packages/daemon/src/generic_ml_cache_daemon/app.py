# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FastAPI application factory for the generic-ml-cache daemon."""

from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable, FrozenSet, Optional, cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from generic_ml_cache_adapters.adapter.out.clock.system_clock import SystemClock
from generic_ml_cache_adapters.adapter.out.crypto.encrypting_blob_store import (
    EncryptingBlobStore,
    TokenRequiredBlobStore,
)
from generic_ml_cache_adapters.adapter.out.crypto.filesystem_encryption_manifest_store import (
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_adapters.adapter.out.crypto.store_encryptor import StoreEncryptor
from generic_ml_cache_adapters.adapter.out.diagnostics.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_adapters.adapter.out.diagnostics.structlog_diagnostics_adapter import (
    StructlogDiagnosticsAdapter,
)
from generic_ml_cache_adapters.adapter.out.fingerprint.filesystem_file_fingerprint import (
    FilesystemFileFingerprint,
)
from generic_ml_cache_adapters.adapter.out.gateway.http_gateway_forward_adapter import (
    HttpGatewayForwardAdapter,
)
from generic_ml_cache_adapters.adapter.out.metrics.access_registry import AccessRegistry
from generic_ml_cache_adapters.adapter.out.metrics.journal_metrics import JournalMetrics
from generic_ml_cache_adapters.adapter.out.persistence.execution_repository import (
    ExecutionRepository,
)
from generic_ml_cache_adapters.adapter.out.persistence.filesystem_store_lock import (
    FilesystemStoreLock,
)
from generic_ml_cache_adapters.adapter.out.storage.filesystem_blob_store import FilesystemBlobStore
from generic_ml_cache_adapters.adapter.out.workspace.filesystem_workspace import FilesystemWorkspace
from generic_ml_cache_adapters.migration_runner import run_migrations
from generic_ml_cache_adapters.discovery.composition import default_catalog, default_resolver
from generic_ml_cache_core.application.usecase.select_adapter_for_execution_service import (
    SelectAdapterForExecutionService,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.inbound.wired_use_cases import WiredUseCases
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.registered_adapter import RegisteredAdapter
from generic_ml_cache_core.application.usecase.probe_service import ProbeService
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.application.usecase.run_ml_execution_service import (
    RunMlExecutionService,
)
from generic_ml_cache_core.application.usecase.run_ml_gateway_service import RunMlGatewayService
from generic_ml_cache_adapters.db import DbConnection
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
}
_LOG_FILE_NAME = "gmlcache.log"


def _db_conn_factory(store_root: Path) -> Callable[[], DbConnection]:
    db_path = store_root / _DB_NAME

    def _connect() -> DbConnection:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return cast(DbConnection, sqlite3.connect(str(db_path), check_same_thread=False))

    return _connect


_CAPTURE_ENV_FLAG = "GMLCACHE_GATEWAY_CAPTURE"
_CAPTURE_ENV_PATH = "GMLCACHE_GATEWAY_CAPTURE_PATH"
_CAPTURE_FILENAME = "gateway-capture.ndjson"


def _resolve_capture_path(store_root: Path) -> Optional[Path]:
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
    session_id: Optional[str] = None,
    enable_metrics: bool = False,
    max_size: Optional[int] = None,
    max_age: Optional[float] = None,
    eviction_interval: float = 3600.0,
    whitelist: Optional[FrozenSet[str]] = None,
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
    if log_level:
        log_file = Path(log_file_env) if log_file_env else store_root / _LOG_FILE_NAME
        log_file.parent.mkdir(parents=True, exist_ok=True)
        _diag = StructlogDiagnosticsAdapter(log_file, level=log_level)
    else:
        _diag = NullDiagnosticsAdapter()
    _conn_factory = _db_conn_factory(store_root)
    _encryption_token = os.environ.get("GMLCACHE_TOKEN") or None
    _blob_dir = store_root / "blobs"
    _raw_store: BlobStorePort = FilesystemBlobStore(_blob_dir)
    _manifest = FilesystemEncryptionManifestStore(store_root).load()
    if _manifest is None:
        _blob_store: BlobStorePort = _raw_store
    elif _encryption_token is None:
        _blob_store = TokenRequiredBlobStore(_raw_store)
    else:
        from generic_ml_cache_adapters.adapter.out.crypto.aesgcm_cipher import AesGcmCipher  # noqa: PLC0415

        _cipher = AesGcmCipher()
        _data_key = _cipher.open_envelope(_encryption_token, _manifest)
        _blob_store = EncryptingBlobStore(_raw_store, _cipher, _data_key)
    StoreEncryptor(
        store_root, FilesystemEncryptionManifestStore(store_root), FilesystemStoreLock(store_root)
    ).recover()
    _clock = SystemClock()
    run_migrations(_conn_factory, _diag)
    _repository = ExecutionRepository(_conn_factory, _clock)
    _metrics = JournalMetrics(AccessRegistry(_conn_factory, diag=_diag))
    _file_fingerprint = FilesystemFileFingerprint()
    # Select claude's adapter from the catalog and resolve it to an instance.
    _descriptor = SelectAdapterForExecutionService(default_catalog()).select(
        "claude", ExecutionKind.LOCAL_MANAGED
    )
    _cli_adapter = cast(
        RegisteredAdapter,
        default_resolver().resolve_local_client(_descriptor.adapter_id),
    )
    # One adapter instance handles both managed and passthrough execution.
    _runners: dict[ExecutionKind, RegisteredAdapter] = {
        ExecutionKind.LOCAL_MANAGED: _cli_adapter,
        ExecutionKind.LOCAL_PASSTHROUGH: _cli_adapter,
    }
    _purge = PurgeService(_repository, _blob_store, _metrics, diag=_diag)
    _gateway_forward = HttpGatewayForwardAdapter()
    _run_gateway = RunMlGatewayService(
        blob_store=_blob_store,
        gateway_forward_port=_gateway_forward,
        repository=_repository,
        metrics=_metrics,
        diag=_diag,
    )
    wired_use_cases = WiredUseCases(
        run_ml=RunMlExecutionService(
            _file_fingerprint,
            _runners,
            _blob_store,
            _repository,
            _metrics,
            purge_service=_purge,
            max_size=max_size,
            workspace=FilesystemWorkspace(),
            diag=_diag,
        ),
        probe=ProbeService(_file_fingerprint, _repository),
        purge=_purge,
        blob_store=_blob_store,
        repository=_repository,
        metrics=_metrics,
        run_gateway=_run_gateway,
        diag=_diag,
    )

    eviction_stats = EvictionStats(
        max_size=max_size,
        max_age=max_age,
        interval=eviction_interval,
    )
    scheduler = EvictionScheduler(
        wired_use_cases.purge,
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

    @application.exception_handler(CacheError)
    async def _cache_error_handler(request: Request, exc: CacheError) -> JSONResponse:
        status = _CACHE_ERROR_HTTP.get(exc.code, 500)
        return JSONResponse(status_code=status, content={"code": exc.code, "detail": str(exc)})

    application.state.wired = wired_use_cases
    application.state.store_root = store_root
    application.state.session_id = session_id
    application.state.enable_metrics = enable_metrics
    application.state.eviction_stats = eviction_stats
    application.state.whitelist = whitelist

    from generic_ml_cache_daemon.jobs import JobRegistry
    from generic_ml_cache_daemon.controllers.executions import router as executions_router
    from generic_ml_cache_daemon.controllers.gateway import router as gateway_router
    from generic_ml_cache_daemon.controllers.health import router as health_router
    from generic_ml_cache_daemon.controllers.jobs import router as jobs_router
    from generic_ml_cache_daemon.controllers.run import router as run_router
    from generic_ml_cache_daemon.controllers.sessions import router as sessions_router

    application.state.job_registry = JobRegistry()
    application.include_router(health_router)
    application.include_router(sessions_router)
    application.include_router(executions_router)
    application.include_router(run_router)
    application.include_router(jobs_router)
    application.include_router(gateway_router)

    capture_path = _resolve_capture_path(store_root)
    if capture_path is not None:
        from generic_ml_cache_daemon.infrastructure.capture import GatewayCaptureMiddleware  # noqa: PLC0415

        application.add_middleware(GatewayCaptureMiddleware, capture_path=capture_path)

    return application
