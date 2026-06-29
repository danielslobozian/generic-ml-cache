# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Private composition root for the CLI.

Assembles all concrete outbound adapters from ``generic_ml_cache_adapters``
and wires the use-case layer.  Nothing outside this module and
``composition.py`` should import from ``generic_ml_cache_adapters.adapter.out``
directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, FrozenSet, Optional, cast

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
from generic_ml_cache_cli.discovery import catalog_for, default_resolver, execution_kind_for
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.usecase.select_adapter_for_execution_service import (
    SelectAdapterForExecutionService,
)
from generic_ml_cache_core.application.port.inbound.wired_use_cases import WiredUseCases
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.out.registered_adapter import RegisteredAdapter
from generic_ml_cache_core.application.usecase.probe_service import ProbeService
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.application.usecase.run_ml_execution_service import (
    RunMlExecutionService,
)
from generic_ml_cache_core.application.usecase.run_ml_gateway_service import RunMlGatewayService
from generic_ml_cache_adapters.db import DbConnection

_BLOBS_DIRNAME = "blobs"

ExecutableOverride = Callable[[str], Optional[str]]


def _recover_store(store_root: Path) -> None:
    StoreEncryptor(
        store_root,
        FilesystemEncryptionManifestStore(store_root),
        FilesystemStoreLock(store_root),
    ).recover()


def _resolve_blob_store(store_root: Path, encryption_token: Optional[str]) -> BlobStorePort:
    blob_store: BlobStorePort = FilesystemBlobStore(store_root / _BLOBS_DIRNAME)
    manifest = FilesystemEncryptionManifestStore(store_root).load()
    if manifest is None:
        return blob_store
    if encryption_token is None:
        return TokenRequiredBlobStore(blob_store)
    from generic_ml_cache_adapters.adapter.out.crypto.aesgcm_cipher import AesGcmCipher  # noqa: PLC0415

    cipher = AesGcmCipher()
    data_key = cipher.open_envelope(encryption_token, manifest)
    return EncryptingBlobStore(blob_store, cipher, data_key)


def _build_runners(
    client: Optional[str],
    kind: Optional[ExecutionKind],
    executable_override: Optional[ExecutableOverride],
    timeout: Optional[float],
    stream_path: Optional[str],
    whitelist: Optional[FrozenSet[str]] = None,
) -> Dict[ExecutionKind, RegisteredAdapter]:
    catalog = catalog_for(whitelist)
    resolver = default_resolver()
    if kind is ExecutionKind.LOCAL_MANAGED:
        assert client is not None
        descriptor = SelectAdapterForExecutionService(catalog).select(
            client, ExecutionKind.LOCAL_MANAGED
        )
        exe_override = executable_override(client) if executable_override else None
        cli_adapter = cast(
            RegisteredAdapter,
            resolver.resolve_local_client(
                descriptor.adapter_id, exe_override, timeout, stream_path
            ),
        )
        # One adapter instance handles both managed and passthrough execution.
        return {
            ExecutionKind.LOCAL_MANAGED: cli_adapter,
            ExecutionKind.LOCAL_PASSTHROUGH: cli_adapter,
        }
    if kind is ExecutionKind.API:
        assert client is not None
        descriptor = SelectAdapterForExecutionService(catalog).select(client, ExecutionKind.API)
        return {
            ExecutionKind.API: cast(
                RegisteredAdapter, resolver.resolve_runner(descriptor.adapter_id)
            )
        }
    from generic_ml_cache_adapters.adapter.out.api.stub_api_client_adapter import (
        StubApiClientAdapter,
    )  # noqa: PLC0415

    return {ExecutionKind.API: StubApiClientAdapter()}


def build_use_cases(
    conn_factory: Callable[[], DbConnection],
    store_root: Path,
    executable_override: Optional[ExecutableOverride] = None,
    timeout: Optional[float] = None,
    encryption_token: Optional[str] = None,
    stream_path: Optional[str] = None,
    client: Optional[str] = None,
    max_size: Optional[int] = None,
    whitelist: Optional[FrozenSet[str]] = None,
    diag: Optional[DiagnosticsPort] = None,
) -> WiredUseCases:
    store_root = Path(store_root)
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    _recover_store(store_root)
    clock = SystemClock()
    blob_store = _resolve_blob_store(store_root, encryption_token)
    run_migrations(conn_factory, _diag)
    repository = ExecutionRepository(conn_factory, clock)
    metrics = JournalMetrics(AccessRegistry(conn_factory, diag=_diag))
    file_fingerprint = FilesystemFileFingerprint()
    kind = execution_kind_for(client, whitelist) if client is not None else None
    runners = _build_runners(
        client, kind, executable_override, timeout, stream_path, whitelist=whitelist
    )
    purge = PurgeService(repository, blob_store, metrics, diag=_diag)
    gateway_forward = HttpGatewayForwardAdapter()
    run_gateway = RunMlGatewayService(
        blob_store=blob_store,
        gateway_forward_port=gateway_forward,
        repository=repository,
        metrics=metrics,
        diag=_diag,
    )
    return WiredUseCases(
        run_ml=RunMlExecutionService(
            file_fingerprint,
            runners,
            blob_store,
            repository,
            metrics,
            purge_service=purge,
            max_size=max_size,
            workspace=FilesystemWorkspace(),
            diag=_diag,
        ),
        probe=ProbeService(file_fingerprint, repository),
        purge=purge,
        blob_store=blob_store,
        repository=repository,
        metrics=metrics,
        run_gateway=run_gateway,
        diag=_diag,
    )


def get_encryption_state(store_root: Path) -> EncryptionState:
    """Return the current encryption state of the store at ``store_root``."""
    return FilesystemEncryptionManifestStore(store_root).state()


def load_cipher():
    """Build the AES-GCM cipher, with a friendly error if the optional extra is missing."""
    try:
        from generic_ml_cache_adapters.adapter.out.crypto.aesgcm_cipher import AesGcmCipher  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "error: encryption needs an optional dependency — install with "
            '`pip install "generic-ml-cache-adapters[encryption]"`'
        ) from exc
    return AesGcmCipher()


def build_store_encryptor(store_root: Path, cipher=None) -> StoreEncryptor:
    """Construct a StoreEncryptor for the store at ``store_root``."""
    return StoreEncryptor(
        store_root,
        FilesystemEncryptionManifestStore(store_root),
        FilesystemStoreLock(store_root),
        cipher,
    )
