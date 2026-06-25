# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PurgeService: retention policy enforcement and explicit cache invalidation."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from generic_ml_cache_core.application.domain.model.purge.purge_report import PurgeReport
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
    ExecutionSizeEntry,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


class PurgeService:
    """Coordinates soft and hard purge operations across the execution store and blob store.

    Soft purge: removes blob files and artifact rows, preserving the execution
    records, token_usage, tags, and access events — statistics and history survive,
    only the stored bytes are released.

    Hard delete: removes every DB row and blob for a key — nothing survives.

    LRU eviction: soft-purges the least-recently-accessed executions until the
    store is at or below the configured size quota. LRU order is derived from the
    access journal; creation timestamp is the fallback for entries never accessed.
    """

    def __init__(
        self,
        repository: ExecutionRepositoryPort,
        blob_store: BlobStorePort,
        metrics: MetricsPort,
    ) -> None:
        self._repository = repository
        self._blob_store = blob_store
        self._metrics = metrics

    # -- soft purge -----------------------------------------------------------

    def purge_one(self, execution_key: str) -> PurgeReport:
        """Soft-purge a single execution by its key. Returns an empty report if
        the key does not exist in the store."""
        if not self._repository.find_all(execution_key):
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        return self._soft_purge_keys([execution_key])

    def purge_by_tag(self, tag: str) -> PurgeReport:
        """Soft-purge all current executions carrying ``tag``."""
        return self._soft_purge_keys(self._repository.executions_by_tag(tag))

    def purge_by_session(self, session_id: str) -> PurgeReport:
        """Soft-purge all executions recorded under ``session_id``."""
        return self._soft_purge_keys(self._metrics.execution_keys_for_session(session_id))

    def purge_all(self) -> PurgeReport:
        """Soft-purge every current execution in the store."""
        keys = [e.execution_key for e in self._repository.current_executions_with_sizes()]
        return self._soft_purge_keys(keys)

    # -- hard delete ----------------------------------------------------------

    def hard_delete_one(self, execution_key: str) -> PurgeReport:
        """Hard-delete a single execution and erase its access history. Returns
        an empty report if the key does not exist in the store."""
        if not self._repository.find_all(execution_key):
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        return self._hard_delete_keys([execution_key])

    def hard_delete_by_tag(self, tag: str) -> PurgeReport:
        """Hard-delete all current executions carrying ``tag``."""
        return self._hard_delete_keys(self._repository.executions_by_tag(tag))

    def hard_delete_by_session(self, session_id: str) -> PurgeReport:
        """Hard-delete all executions recorded under ``session_id``."""
        return self._hard_delete_keys(self._metrics.execution_keys_for_session(session_id))

    def hard_delete_all(self) -> PurgeReport:
        """Hard-delete every execution in the store, including failed-only keys."""
        return self._hard_delete_keys(self._repository.all_execution_keys())

    # -- quota enforcement ----------------------------------------------------

    def evict_to_quota(self, max_bytes: int) -> PurgeReport:
        """Soft-purge the least-recently-accessed executions until the store is at
        or below ``max_bytes``. Returns an empty report when already under quota."""
        current = self._repository.total_stored_bytes()
        if current <= max_bytes:
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)

        entries = self._repository.current_executions_with_sizes()
        last_access = self._metrics.last_access()
        sorted_entries = sorted(entries, key=lambda e: _lru_epoch(e, last_access))

        keys_to_evict: List[str] = []
        running = current
        for entry in sorted_entries:
            if running <= max_bytes:
                break
            keys_to_evict.append(entry.execution_key)
            running -= entry.total_size_bytes

        return self._soft_purge_keys(keys_to_evict)

    # -- private --------------------------------------------------------------

    def _soft_purge_keys(self, keys: List[str]) -> PurgeReport:
        if not keys:
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        before = self._repository.total_stored_bytes()
        all_blob_keys: List[str] = []
        for key in keys:
            all_blob_keys.extend(self._repository.blob_keys_for_execution(key))
            self._repository.soft_purge_execution(key)
        after = self._repository.total_stored_bytes()
        blobs_removed = self._remove_orphaned_blobs(all_blob_keys)
        return PurgeReport(
            executions_removed=len(keys),
            bytes_freed=max(0, before - after),
            blobs_removed=blobs_removed,
        )

    def _hard_delete_keys(self, keys: List[str]) -> PurgeReport:
        if not keys:
            return PurgeReport(executions_removed=0, bytes_freed=0, blobs_removed=0)
        before = self._repository.total_stored_bytes()
        all_blob_keys: List[str] = []
        for key in keys:
            all_blob_keys.extend(self._repository.blob_keys_for_execution(key))
            self._repository.hard_delete_execution(key)
            self._metrics.delete_events_for_key(key)
        after = self._repository.total_stored_bytes()
        blobs_removed = self._remove_orphaned_blobs(all_blob_keys)
        return PurgeReport(
            executions_removed=len(keys),
            bytes_freed=max(0, before - after),
            blobs_removed=blobs_removed,
        )

    def _remove_orphaned_blobs(self, blob_keys: List[str]) -> int:
        removed = 0
        for blob_key in set(blob_keys):
            if self._repository.blob_reference_count(blob_key) == 0:
                self._blob_store.remove(blob_key)
                removed += 1
        return removed


def _lru_epoch(entry: ExecutionSizeEntry, last_access: Dict[str, float]) -> float:
    if entry.execution_key in last_access:
        return last_access[entry.execution_key]
    try:
        return datetime.fromisoformat(entry.created_at).timestamp()
    except (ValueError, AttributeError):
        return 0.0
