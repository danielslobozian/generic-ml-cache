# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""build_application_api — the shared composition root.

The ~15-object assembly that turns a store location + a connection factory into
a wired :class:`ApplicationApi` was duplicated, almost line for line, between the
CLI's ``_compose.py`` and the daemon's ``app.py``. It lives here now, in the one
package allowed to import both ``core`` and the concrete ``adapters``.

Only one thing genuinely differs between the drivers: **which client adapters to
wire**. The CLI runs one selected client per invocation; the daemon wires every
whitelisted client. That single variation is injected as the ``build_runners``
strategy; everything else (store recovery, blob store + encryption, migrations,
repository, metrics, gateway, the use-case graph) is identical and lives here.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from generic_ml_cache_adapters.adapter.outbound.clock.system_clock import SystemClock
from generic_ml_cache_adapters.adapter.outbound.crypto.encrypting_blob_store import (
    EncryptingBlobStore,
    TokenRequiredBlobStore,
)
from generic_ml_cache_adapters.adapter.outbound.crypto.filesystem_encryption_manifest_store import (
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_adapters.adapter.outbound.crypto.store_encryptor import StoreEncryptor
from generic_ml_cache_adapters.adapter.outbound.diagnostics.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_adapters.adapter.outbound.fingerprint.filesystem_file_fingerprint import (
    FilesystemFileFingerprint,
)
from generic_ml_cache_adapters.adapter.outbound.gateway.http_gateway_forward_adapter import (
    HttpGatewayForwardAdapter,
)
from generic_ml_cache_adapters.adapter.outbound.metrics.access_registry import AccessRegistry
from generic_ml_cache_adapters.adapter.outbound.metrics.journal_metrics import JournalMetrics
from generic_ml_cache_adapters.adapter.outbound.persistence.filesystem_store_lock import (
    FilesystemStoreLock,
)
from generic_ml_cache_adapters.adapter.outbound.persistence.sqlite.execution_repository import (
    SqliteExecutionRepository,
)
from generic_ml_cache_adapters.adapter.outbound.storage.filesystem_blob_store import (
    FilesystemBlobStore,
)
from generic_ml_cache_adapters.adapter.outbound.workspace.filesystem_workspace import (
    FilesystemWorkspace,
)
from generic_ml_cache_adapters.db import DbConnection
from generic_ml_cache_adapters.migration_runner import run_migrations
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.registered_adapter_port import (
    RegisteredAdapterPort,
)
from generic_ml_cache_core.application.usecase.artifact_content_service import (
    ArtifactContentService,
)
from generic_ml_cache_core.application.usecase.execution_query_service import ExecutionQueryService
from generic_ml_cache_core.application.usecase.probe_service import ProbeService
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.application.usecase.run_ml_execution_service import (
    RunMlExecutionService,
)
from generic_ml_cache_core.application.usecase.run_ml_gateway_service import RunMlGatewayService
from generic_ml_cache_core.application.usecase.session_admin_service import SessionAdminService
from generic_ml_cache_core.application.usecase.session_report_service import SessionReportService
from generic_ml_cache_core.application.usecase.session_tags_service import SessionTagsService
from generic_ml_cache_core.application.usecase.store_stats_service import StoreStatsService
from generic_ml_cache_core.application.wiring.application_api import ApplicationApi

from generic_ml_cache_bootstrap.discovery.composition import catalog_for, default_resolver

_BLOBS_DIRNAME = "blobs"

# The driver-specific variation: given the resolved catalog + resolver, return the
# runner adapters to wire, keyed by client NAME. (CLI: one selected client; daemon:
# all whitelisted.)
BuildRunners = Callable[[AdapterCatalogPort, AdapterResolverPort], dict[str, RegisteredAdapterPort]]


def recover_store(store_root: Path) -> None:
    """Roll back any half-finished encryption migration before the store is read."""
    StoreEncryptor(
        store_root,
        FilesystemEncryptionManifestStore(store_root),
        FilesystemStoreLock(store_root),
    ).recover()


def resolve_blob_store(store_root: Path, encryption_token: str | None) -> BlobStorePort:
    """The blob store, wrapped for encryption when the store has a manifest."""
    blob_store: BlobStorePort = FilesystemBlobStore(store_root / _BLOBS_DIRNAME)
    manifest = FilesystemEncryptionManifestStore(store_root).load()
    if manifest is None:
        return blob_store
    if encryption_token is None:
        return TokenRequiredBlobStore(blob_store)
    from generic_ml_cache_adapters.adapter.outbound.crypto.aesgcm_cipher import AesGcmCipher

    cipher = AesGcmCipher()
    data_key = cipher.open_envelope(encryption_token, manifest)
    return EncryptingBlobStore(blob_store, cipher, data_key)


def build_application_api(
    conn_factory: Callable[[], DbConnection],
    store_root: Path,
    build_runners: BuildRunners,
    *,
    encryption_token: str | None = None,
    max_size: int | None = None,
    whitelist: frozenset[str] | None = None,
    diag: DiagnosticsPort | None = None,
) -> ApplicationApi:
    """Wire the application: every outbound adapter + the use-case graph.

    ``build_runners`` is the only driver-specific input — it chooses which client
    adapters to wire from the resolved catalog/resolver.
    """
    store_root = Path(store_root)
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    recover_store(store_root)
    clock = SystemClock()
    blob_store = resolve_blob_store(store_root, encryption_token)
    run_migrations(conn_factory, _diag)
    repository = SqliteExecutionRepository(conn_factory, clock)
    metrics = JournalMetrics(AccessRegistry(conn_factory, diag=_diag))
    file_fingerprint = FilesystemFileFingerprint()
    runners = build_runners(catalog_for(whitelist), default_resolver())
    # One application service per capability (grouped by shared machinery); each
    # is exposed through the segregated per-operation inbound-port fields of
    # ApplicationApi (B-1), so the same instance is bound to several fields.
    purge = PurgeService(repository, blob_store, metrics, diag=_diag)
    session_tags = SessionTagsService(metrics)
    session_admin = SessionAdminService(metrics)
    session_report = SessionReportService(metrics, repository)
    execution_query = ExecutionQueryService(repository)
    store_stats = StoreStatsService(metrics)
    artifact_content = ArtifactContentService(blob_store)
    run_gateway = RunMlGatewayService(
        blob_store=blob_store,
        gateway_forward_port=HttpGatewayForwardAdapter(),
        repository=repository,
        metrics=metrics,
        diag=_diag,
    )
    return ApplicationApi(
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
        run_gateway=run_gateway,
        purge_by_key=purge,
        purge_by_tag=purge,
        purge_by_session=purge,
        purge_by_session_tag=purge,
        purge_all=purge,
        evict_stale=purge,
        evict_to_quota=purge,
        tag_session=session_tags,
        untag_session=session_tags,
        list_session_tags=session_tags,
        set_session_spec=session_admin,
        clear_session_spec=session_admin,
        get_session_spec=session_admin,
        list_session_ids=session_admin,
        sessions_for_tag=session_admin,
        execution_keys_for_session=session_admin,
        report_for_session=session_report,
        report_for_tag=session_report,
        list_execution_summaries=execution_query,
        total_stored_bytes=execution_query,
        tags_for_execution=execution_query,
        find_current_execution=execution_query,
        find_executions_by_key_prefix=execution_query,
        event_counts=store_stats,
        hit_counts_by_key=store_stats,
        read_artifact_blob=artifact_content,
    )
