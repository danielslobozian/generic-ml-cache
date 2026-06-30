# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PurgeService: retention policy enforcement and explicit cache invalidation."""

from __future__ import annotations

import time
from datetime import datetime

from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from generic_ml_cache_core.application.port.inbound.purge.evict_stale_command import (
    EvictStaleCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.evict_stale_use_case import (
    EvictStaleUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.evict_to_quota_command import (
    EvictToQuotaCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.evict_to_quota_use_case import (
    EvictToQuotaUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_all_command import PurgeAllCommand
from generic_ml_cache_core.application.port.inbound.purge.purge_all_use_case import PurgeAllUseCase
from generic_ml_cache_core.application.port.inbound.purge.purge_by_key_command import (
    PurgeByKeyCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_key_use_case import (
    PurgeByKeyUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_command import (
    PurgeBySessionCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_tag_command import (
    PurgeBySessionTagCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_tag_use_case import (
    PurgeBySessionTagUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_use_case import (
    PurgeBySessionUseCase,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_tag_command import (
    PurgeByTagCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_tag_use_case import (
    PurgeByTagUseCase,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
    ExecutionSizeEntry,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


class PurgeService(
    PurgeByKeyUseCase,
    PurgeByTagUseCase,
    PurgeBySessionUseCase,
    PurgeBySessionTagUseCase,
    PurgeAllUseCase,
    EvictStaleUseCase,
    EvictToQuotaUseCase,
):
    """Coordinates soft and hard purge operations across the execution + blob stores.

    Each scope is one inbound use case; ``hard`` is a command field, not a separate
    use case. Soft purge releases the stored bytes (blobs + artifact rows) but keeps
    the execution records, usage, tags, and access history; hard delete removes
    everything for the key, including its access events. LRU eviction soft-purges
    the least-recently-accessed executions until the store is under quota.
    """

    def __init__(
        self,
        repository: ExecutionRepositoryPort,
        blob_store: BlobStorePort,
        metrics: MetricsPort,
        diag: DiagnosticsPort | None = None,
    ) -> None:
        self._repository = repository
        self._blob_store = blob_store
        self._metrics = metrics
        self._diag: DiagnosticsPort | None = diag

    # -- scoped purge (soft by default; hard when the command says so) ---------

    def purge_by_key(self, command: PurgeByKeyCommand) -> PurgeReport:
        if not self._repository.find_all(command.execution_key):
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        return self._purge([command.execution_key], command.hard)

    def purge_by_tag(self, command: PurgeByTagCommand) -> PurgeReport:
        return self._purge(self._repository.executions_by_tag(command.tag), command.hard)

    def purge_by_session(self, command: PurgeBySessionCommand) -> PurgeReport:
        return self._purge(
            self._metrics.execution_keys_for_session(command.session_id), command.hard
        )

    def purge_by_session_tag(self, command: PurgeBySessionTagCommand) -> PurgeReport:
        return self._purge(self._keys_for_session_tag(command.tag), command.hard)

    def purge_all(self, command: PurgeAllCommand) -> PurgeReport:
        if command.hard:
            # Hard delete-all reaches every key, including failed-only ones.
            keys = self._repository.all_execution_keys()
        else:
            keys = [e.execution_key for e in self._repository.current_executions_with_sizes()]
        return self._purge(keys, command.hard)

    # -- quota / age eviction (always soft) -----------------------------------

    def evict_stale(self, command: EvictStaleCommand) -> PurgeReport:
        """Soft-purge current executions not accessed within ``max_age_seconds``."""
        if command.max_age_seconds <= 0:
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        cutoff = time.time() - command.max_age_seconds
        entries = self._repository.current_executions_with_sizes()
        last_access = self._metrics.last_access()
        stale_keys = [e.execution_key for e in entries if _lru_epoch(e, last_access) < cutoff]
        if stale_keys and self._diag:
            self._diag.info("stale eviction triggered", stale_count=len(stale_keys))
        return self._soft_purge_keys(stale_keys)

    def evict_to_quota(self, command: EvictToQuotaCommand) -> PurgeReport:
        """Soft-purge the least-recently-accessed executions until under ``max_bytes``."""
        current = self._repository.total_stored_bytes()
        if current <= command.max_bytes:
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        entries = self._repository.current_executions_with_sizes()
        last_access = self._metrics.last_access()
        sorted_entries = sorted(entries, key=lambda e: _lru_epoch(e, last_access))
        keys_to_evict: list[str] = []
        running = current
        for entry in sorted_entries:
            if running <= command.max_bytes:
                break
            keys_to_evict.append(entry.execution_key)
            running -= entry.total_size_bytes
        if self._diag:
            self._diag.info(
                "quota eviction triggered",
                current_bytes=current,
                max_bytes=command.max_bytes,
                keys_to_evict=len(keys_to_evict),
            )
        return self._soft_purge_keys(keys_to_evict)

    # -- private --------------------------------------------------------------

    def _purge(self, keys: list[str], hard: bool) -> PurgeReport:
        return self._hard_delete_keys(keys) if hard else self._soft_purge_keys(keys)

    def _soft_purge_keys(self, keys: list[str]) -> PurgeReport:
        if not keys:
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        before = self._repository.total_stored_bytes()
        all_blob_keys: list[str] = []
        for key in keys:
            all_blob_keys.extend(self._repository.blob_keys_for_execution(key))
            self._repository.soft_purge_execution(key)
        after = self._repository.total_stored_bytes()
        report = PurgeReport(
            executions_removed=len(keys),
            bytes_freed=max(0, before - after),
            blobs_removed=self._remove_orphaned_blobs(all_blob_keys),
        )
        if self._diag:
            self._diag.info(
                "soft-purge complete",
                executions=report.executions_removed,
                bytes_freed=report.bytes_freed,
                blobs_removed=report.blobs_removed,
            )
        return report

    def _hard_delete_keys(self, keys: list[str]) -> PurgeReport:
        if not keys:
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        before = self._repository.total_stored_bytes()
        all_blob_keys: list[str] = []
        for key in keys:
            all_blob_keys.extend(self._repository.blob_keys_for_execution(key))
            self._repository.hard_delete_execution(key)
            self._metrics.delete_events_for_key(key)
        after = self._repository.total_stored_bytes()
        report = PurgeReport(
            executions_removed=len(keys),
            bytes_freed=max(0, before - after),
            blobs_removed=self._remove_orphaned_blobs(all_blob_keys),
        )
        if self._diag:
            self._diag.info(
                "hard-delete complete",
                executions=report.executions_removed,
                bytes_freed=report.bytes_freed,
                blobs_removed=report.blobs_removed,
            )
        return report

    def _keys_for_session_tag(self, tag: str) -> list[str]:
        seen: set = set()
        keys: list[str] = []
        for session_id in self._metrics.session_ids_for_tag(tag):
            for key in self._metrics.execution_keys_for_session(session_id):
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        return keys

    def _remove_orphaned_blobs(self, blob_keys: list[str]) -> int:
        removed = 0
        for blob_key in set(blob_keys):
            if self._repository.blob_reference_count(blob_key) == 0:
                self._blob_store.remove(blob_key)
                removed += 1
        return removed


def _lru_epoch(entry: ExecutionSizeEntry, last_access: dict[str, float]) -> float:
    if entry.execution_key in last_access:
        return last_access[entry.execution_key]
    try:
        return datetime.fromisoformat(entry.created_at).timestamp()
    except (ValueError, AttributeError):
        return 0.0
