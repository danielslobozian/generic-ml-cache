# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The composition root: build the real adapters and wire the use cases.

This is the *only* place that names every concrete adapter. It reads where to
store things, constructs the outbound adapters, and hands them to the use-case
services through their constructors. A driving adapter (the CLI) asks for the
wired use cases and depends only on the inbound ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from generic_ml_cache.adapter.out.api.stub_api_client_adapter import StubApiClientAdapter
from generic_ml_cache.adapter.out.client.local_client_runner import LocalClientRunner
from generic_ml_cache.adapter.out.client.passthrough_client_runner import (
    PassthroughClientRunner,
)
from generic_ml_cache.adapter.out.clock.system_clock import SystemClock
from generic_ml_cache.adapter.out.fingerprint.filesystem_file_fingerprint import (
    FilesystemFileFingerprint,
)
from generic_ml_cache.adapter.out.metrics.access_registry import AccessRegistry
from generic_ml_cache.adapter.out.metrics.journal_metrics import JournalMetrics
from generic_ml_cache.adapter.out.persistence.sqlite_execution_repository import (
    SqliteExecutionRepository,
)
from generic_ml_cache.adapter.out.storage.filesystem_blob_store import FilesystemBlobStore
from generic_ml_cache.application.usecase.probe_service import ProbeService
from generic_ml_cache.application.usecase.run_api_execution_service import RunApiExecutionService
from generic_ml_cache.application.usecase.run_managed_local_execution_service import (
    RunManagedLocalExecutionService,
)
from generic_ml_cache.application.usecase.run_passthrough_execution_service import (
    RunPassthroughExecutionService,
)

_BLOBS_DIRNAME = "blobs"
_EXECUTIONS_DB = "executions.sqlite3"

#: given a client name, the executable override to use, or None for the default.
ExecutableOverride = Callable[[str], Optional[str]]


@dataclass(frozen=True)
class WiredUseCases:
    """The use cases a driving adapter needs, plus the stores the read-only CLI
    views (inspect/stats/list) query directly."""

    run_managed: RunManagedLocalExecutionService
    run_passthrough: RunPassthroughExecutionService
    run_api: RunApiExecutionService
    probe: ProbeService
    blob_store: FilesystemBlobStore
    repository: SqliteExecutionRepository
    metrics: JournalMetrics


def build_use_cases(
    store_root: Path,
    executable_override: Optional[ExecutableOverride] = None,
    timeout: Optional[float] = None,
) -> WiredUseCases:
    """Construct the outbound adapters under ``store_root`` and wire the services.

    Layout: ``store_root/blobs/`` for output bytes, ``store_root/executions.sqlite3``
    for the structured records, and the access-event registry beside them.
    """
    store_root = Path(store_root)
    clock = SystemClock()
    blob_store = FilesystemBlobStore(store_root / _BLOBS_DIRNAME)
    repository = SqliteExecutionRepository(store_root / _EXECUTIONS_DB, clock)
    metrics = JournalMetrics(AccessRegistry(store_root))
    file_fingerprint = FilesystemFileFingerprint()
    local_runner = LocalClientRunner(executable_override, timeout)
    passthrough_runner = PassthroughClientRunner(executable_override, timeout)
    api_client = StubApiClientAdapter()

    return WiredUseCases(
        run_managed=RunManagedLocalExecutionService(
            file_fingerprint, local_runner, blob_store, repository, metrics
        ),
        run_passthrough=RunPassthroughExecutionService(
            passthrough_runner, blob_store, repository, metrics
        ),
        run_api=RunApiExecutionService(api_client, blob_store, repository, metrics),
        probe=ProbeService(file_fingerprint, repository),
        blob_store=blob_store,
        repository=repository,
        metrics=metrics,
    )
