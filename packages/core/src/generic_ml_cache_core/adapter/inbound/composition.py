# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The composition root: build the real adapters and wire the use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Optional

from generic_ml_cache_core.adapter.out.api.api_discover import list_api_models
from generic_ml_cache_core.adapter.out.clock.system_clock import SystemClock
from generic_ml_cache_core.adapter.out.client.discover import (
    list_models,
    list_models_all,
    probe_all,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.execution_repository_port import ExecutionRepositoryPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.adapter.out.fingerprint.filesystem_file_fingerprint import (
    FilesystemFileFingerprint,
)
from generic_ml_cache_core.adapter.out.metrics.access_registry import AccessRegistry
from generic_ml_cache_core.adapter.out.metrics.journal_metrics import JournalMetrics
from generic_ml_cache_core.adapter.out.persistence.sqlite_execution_repository import (
    SqliteExecutionRepository,
)
from generic_ml_cache_core.adapter.out.crypto.encrypting_blob_store import (
    EncryptingBlobStore,
    TokenRequiredBlobStore,
)
from generic_ml_cache_core.adapter.out.crypto.filesystem_encryption_manifest_store import (
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_core.adapter.out.crypto.store_encryptor import StoreEncryptor
from generic_ml_cache_core.adapter.out.persistence.sqlite_store_lock import SqliteStoreLock
from generic_ml_cache_core.adapter.out.storage.filesystem_blob_store import FilesystemBlobStore
from generic_ml_cache_core.application.usecase.probe_service import ProbeService
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.adapter.out.gateway.http_gateway_forward_adapter import (
    HttpGatewayForwardAdapter,
)
from generic_ml_cache_core.application.usecase.run_ml_execution_service import RunMlExecutionService
from generic_ml_cache_core.application.usecase.run_ml_gateway_service import RunMlGatewayService

_BLOBS_DIRNAME = "blobs"
_EXECUTIONS_DB = "executions.sqlite3"

ExecutableOverride = Callable[[str], Optional[str]]


@dataclass(frozen=True)
class WiredUseCases:
    run_ml: RunMlExecutionService
    probe: ProbeService
    purge: PurgeService
    blob_store: BlobStorePort
    repository: ExecutionRepositoryPort
    metrics: MetricsPort
    run_gateway: RunMlGatewayService


def _recover_store(store_root: Path) -> None:
    StoreEncryptor(
        store_root,
        FilesystemEncryptionManifestStore(store_root),
        SqliteStoreLock(store_root),
    ).recover()


def _resolve_blob_store(store_root: Path, encryption_token: Optional[str]) -> BlobStorePort:
    blob_store: BlobStorePort = FilesystemBlobStore(store_root / _BLOBS_DIRNAME)
    manifest = FilesystemEncryptionManifestStore(store_root).load()
    if manifest is None:
        return blob_store
    if encryption_token is None:
        return TokenRequiredBlobStore(blob_store)
    from generic_ml_cache_core.adapter.out.crypto.aesgcm_cipher import AesGcmCipher

    cipher = AesGcmCipher()
    data_key = cipher.open_envelope(encryption_token, manifest)
    return EncryptingBlobStore(blob_store, cipher, data_key)


def resolve_execution_kind(
    client: str, whitelist: Optional[FrozenSet[str]] = None
) -> ExecutionKind:
    """Return the execution kind for ``client`` via the unified adapter registry."""
    from generic_ml_cache_core.adapter.registry import get_adapter

    return get_adapter(client, whitelist=whitelist).execution_kind


def _build_runners(
    client: Optional[str],
    kind: Optional[ExecutionKind],
    executable_override: Optional[ExecutableOverride],
    timeout: Optional[float],
    stream_path: Optional[str],
    whitelist: Optional[FrozenSet[str]] = None,
) -> Dict[ExecutionKind, MlRunnerPort]:
    """Build the runners dict for the given client and kind."""
    if kind is ExecutionKind.LOCAL_MANAGED:
        from generic_ml_cache_core.adapter.registry import get_adapter
        from generic_ml_cache_core.adapter.out.client.abstract_passthrough_local_adapter import (
            AbstractPassthroughLocalAdapter,
        )

        registered = get_adapter(client, whitelist=whitelist)
        cls = type(registered)
        exe_override = executable_override(client) if executable_override else None
        managed = cls(executable_override=exe_override, timeout=timeout, stream_path=stream_path)
        passthrough = AbstractPassthroughLocalAdapter(registered, exe_override, timeout)
        return {
            ExecutionKind.LOCAL_MANAGED: managed,
            ExecutionKind.LOCAL_PASSTHROUGH: passthrough,
        }
    if kind is ExecutionKind.API:
        from generic_ml_cache_core.adapter.registry import get_adapter

        return {ExecutionKind.API: get_adapter(client, whitelist=whitelist)}
    # client=None: provide a stub API runner so cache-replay and management commands
    # can still serve API-kind executions from the store without a real provider.
    from generic_ml_cache_core.adapter.out.api.stub_api_client_adapter import StubApiClientAdapter

    return {ExecutionKind.API: StubApiClientAdapter()}


def build_use_cases(
    store_root: Path,
    executable_override: Optional[ExecutableOverride] = None,
    timeout: Optional[float] = None,
    encryption_token: Optional[str] = None,
    stream_path: Optional[str] = None,
    client: Optional[str] = None,
    max_size: Optional[int] = None,
    whitelist: Optional[FrozenSet[str]] = None,
) -> WiredUseCases:
    store_root = Path(store_root)
    _recover_store(store_root)
    clock = SystemClock()
    blob_store = _resolve_blob_store(store_root, encryption_token)
    repository = SqliteExecutionRepository(store_root / _EXECUTIONS_DB, clock)
    metrics = JournalMetrics(AccessRegistry(store_root))
    file_fingerprint = FilesystemFileFingerprint()
    kind = resolve_execution_kind(client, whitelist=whitelist) if client is not None else None
    runners = _build_runners(
        client, kind, executable_override, timeout, stream_path, whitelist=whitelist
    )
    purge = PurgeService(repository, blob_store, metrics)
    gateway_forward = HttpGatewayForwardAdapter()
    run_gateway = RunMlGatewayService(
        blob_store=blob_store,
        gateway_forward_port=gateway_forward,
        repository=repository,
        metrics=metrics,
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
        ),
        probe=ProbeService(file_fingerprint, repository),
        purge=purge,
        blob_store=blob_store,
        repository=repository,
        metrics=metrics,
        run_gateway=run_gateway,
    )
