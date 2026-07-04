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
from generic_ml_cache_adapters.adapter.outbound.persistence.filesystem_store_lock import (
    FilesystemStoreLock,
)
from generic_ml_cache_adapters.adapter.outbound.storage.filesystem_blob_store import (
    FilesystemBlobStore,
)
from generic_ml_cache_adapters.adapter.outbound.workspace.filesystem_workspace import (
    FilesystemWorkspace,
)
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import AdapterCatalogPort
from generic_ml_cache_core.application.port.outbound.adapter_resolver_port import (
    AdapterResolverPort,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.file_fingerprint_port import (
    FileFingerprintPort,
)
from generic_ml_cache_core.application.port.outbound.gateway_forward_port import GatewayForwardPort
from generic_ml_cache_core.application.port.outbound.registered_adapter_port import (
    RegisteredAdapterPort,
)
from generic_ml_cache_core.application.port.outbound.store_migration_port import (
    CURRENT_MODEL_VERSION,
    StoreMigrationPort,
)
from generic_ml_cache_core.application.usecase.artifact_content_service import (
    ArtifactContentService,
)
from generic_ml_cache_core.application.usecase.execution_query_service import ExecutionQueryService
from generic_ml_cache_core.application.usecase.probe_service import ProbeService
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.application.usecase.repair_store_service import RepairStoreService
from generic_ml_cache_core.application.usecase.run_ml_execution_service import (
    RunMlExecutionService,
)
from generic_ml_cache_core.application.usecase.run_ml_gateway_service import RunMlGatewayService
from generic_ml_cache_core.application.usecase.session_admin_service import SessionAdminService
from generic_ml_cache_core.application.usecase.session_report_service import SessionReportService
from generic_ml_cache_core.application.usecase.session_tags_service import SessionTagsService
from generic_ml_cache_core.application.usecase.store_stats_service import StoreStatsService
from generic_ml_cache_core.application.wiring.application_api import ApplicationApi
from generic_ml_cache_core.common.errors import PersistenceContractOutdated

from generic_ml_cache_bootstrap.discovery.composition import catalog_for, default_resolver
from generic_ml_cache_bootstrap.persistence_backend import (
    PersistenceBackend,
    sqlite_persistence_backend,
)

_BLOBS_DIRNAME = "blobs"
#: The shipped SQLite store's database filename under the store root — used to build
#: the default PersistenceBackend when an embedder injects none.
_DB_NAME = "executions.sqlite3"

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


def provision_store(migration: StoreMigrationPort) -> None:
    """Run the persistence-contract handshake (C-2), then migrate.

    Fail-fast at boot if the injected adapter implements an older model contract
    than this build requires, rather than letting a stale mapping silently drop a
    field. The shipped SQLite adapter is always current; the check guards a
    third-party adapter that might lag ``CURRENT_MODEL_VERSION``.
    """
    implemented = migration.implemented_version()
    if implemented < CURRENT_MODEL_VERSION:
        raise PersistenceContractOutdated(
            f"persistence adapter implements model version {implemented}, but this build "
            f"requires version {CURRENT_MODEL_VERSION}; upgrade the adapter's mapping/migrations"
        )
    migration.migrate_to_current()


def build_application_api(
    store_root: Path,
    build_runners: BuildRunners,
    *,
    persistence: PersistenceBackend | None = None,
    blob_store: BlobStorePort | None = None,
    file_fingerprint: FileFingerprintPort | None = None,
    gateway_forward: GatewayForwardPort | None = None,
    encryption_token: str | None = None,
    max_size: int | None = None,
    whitelist: frozenset[str] | None = None,
    diag: DiagnosticsPort | None = None,
) -> ApplicationApi:
    """Wire the application: the use-case graph over its outbound adapters.

    ``build_runners`` is the only required driver-specific input — it chooses which
    client adapters to wire. The infrastructure adapters are OVERRIDABLE with shipped
    defaults (V33, ``@ConditionalOnMissingBean``): the DB-backed adapters as one
    ``PersistenceBackend`` bundle (default = SQLite under ``store_root``), and the
    blob store / file fingerprint / gateway individually. A standalone driver injects
    nothing and gets the batteries-included SQLite + filesystem stack; an embedder
    supplies a Postgres/S3 backend and the C-2 boot handshake validates it.
    """
    store_root = Path(store_root)
    _diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()
    recover_store(store_root)
    persistence = persistence or sqlite_persistence_backend(store_root / _DB_NAME, _diag)
    blob_store = (
        blob_store if blob_store is not None else resolve_blob_store(store_root, encryption_token)
    )
    file_fingerprint = (
        file_fingerprint if file_fingerprint is not None else FilesystemFileFingerprint()
    )
    gateway_forward = (
        gateway_forward if gateway_forward is not None else HttpGatewayForwardAdapter()
    )
    provision_store(persistence.migration)
    runners = build_runners(catalog_for(whitelist), default_resolver())
    # One application service per capability (grouped by shared machinery); each is
    # exposed through the segregated per-operation inbound-port fields of ApplicationApi
    # (B-1). On the outbound side (V32/V33) each service depends only on the role ports
    # it needs, drawn from the PersistenceBackend bundle's per-role fields (one impl
    # instance backs several of them).
    purge = PurgeService(
        persistence.purge_ml_runs,
        blob_store,
        journal=persistence.purge_journal,
        sessions=persistence.session_query,
        diag=_diag,
    )
    session_tags = SessionTagsService(persistence.session_tags)
    session_admin = SessionAdminService(
        specs=persistence.session_spec, sessions=persistence.session_query
    )
    session_report = SessionReportService(
        report_source=persistence.session_report_source,
        sessions=persistence.session_query,
        repository=persistence.read_ml_run,
        repair_source=persistence.repair_ml_runs,
    )
    execution_query = ExecutionQueryService(persistence.inspect_ml_runs)
    store_stats = StoreStatsService(persistence.call_stats)
    artifact_content = ArtifactContentService(blob_store)
    repair_store = RepairStoreService(
        repair_source=persistence.repair_ml_runs,
        save=persistence.save_ml_run,
        blob_store=blob_store,
    )
    run_gateway = RunMlGatewayService(
        blob_store=blob_store,
        gateway_forward_port=gateway_forward,
        repository=persistence.save_ml_run,
        metrics=persistence.record_call_event,
        diag=_diag,
    )
    return ApplicationApi(
        run_ml=RunMlExecutionService(
            file_fingerprint,
            runners,
            blob_store,
            save=persistence.save_ml_run,
            read=persistence.read_ml_run,
            annotate=persistence.annotate_ml_run,
            record=persistence.record_call_event,
            purge_service=purge,
            max_size=max_size,
            workspace=FilesystemWorkspace(),
            diag=_diag,
        ),
        probe=ProbeService(file_fingerprint, persistence.read_ml_run),
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
        repair_store=repair_store,
    )
