# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import time
from unittest.mock import create_autospec

from generic_ml_cache_core.application.port.inbound.purge.evict_stale_command import (
    EvictStaleCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.evict_to_quota_command import (
    EvictToQuotaCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_all_command import PurgeAllCommand
from generic_ml_cache_core.application.port.inbound.purge.purge_by_key_command import (
    PurgeByKeyCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_command import (
    PurgeBySessionCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_tag_command import (
    PurgeBySessionTagCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_tag_command import (
    PurgeByTagCommand,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
    ExecutionSizeEntry,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.usecase.purge_service import PurgeService


def _make_svc(repo=None, blob=None, metrics=None):
    return PurgeService(
        repository=repo or create_autospec(ExecutionRepositoryPort),
        blob_store=blob or create_autospec(BlobStorePort),
        metrics=metrics or create_autospec(MetricsPort),
    )


def _repo_with_key():
    """Repository mock that has one existing key and no blobs."""
    repo = create_autospec(ExecutionRepositoryPort)
    repo.find_all.return_value = [object()]
    repo.blob_keys_for_execution.return_value = []
    repo.total_stored_bytes.return_value = 0
    return repo


class TestPurgeOne:
    def test_key_exists_calls_soft_purge(self):
        repo = _repo_with_key()
        svc = _make_svc(repo=repo)

        svc.purge_by_key(PurgeByKeyCommand("key1"))

        repo.soft_purge_execution.assert_called_once_with("key1")

    def test_key_exists_report_has_executions_removed_1(self):
        repo = _repo_with_key()
        svc = _make_svc(repo=repo)

        report = svc.purge_by_key(PurgeByKeyCommand("key1"))

        assert report.executions_removed == 1

    def test_key_not_found_returns_empty_report(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_all.return_value = []
        svc = _make_svc(repo=repo)

        report = svc.purge_by_key(PurgeByKeyCommand("missing"))

        assert report.executions_removed == 0
        assert report.bytes_freed == 0
        assert report.blobs_removed == 0

    def test_key_not_found_does_not_call_soft_purge(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_all.return_value = []
        svc = _make_svc(repo=repo)

        svc.purge_by_key(PurgeByKeyCommand("missing"))

        repo.soft_purge_execution.assert_not_called()


class TestPurgeByTag:
    def test_tag_with_keys_soft_purges_each(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.executions_by_tag.return_value = ["key1", "key2"]
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        svc = _make_svc(repo=repo)

        report = svc.purge_by_tag(PurgeByTagCommand("my-tag"))

        assert report.executions_removed == 2
        repo.soft_purge_execution.assert_any_call("key1")
        repo.soft_purge_execution.assert_any_call("key2")

    def test_tag_with_no_keys_returns_empty_report(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.executions_by_tag.return_value = []
        svc = _make_svc(repo=repo)

        report = svc.purge_by_tag(PurgeByTagCommand("empty-tag"))

        assert report.executions_removed == 0
        repo.soft_purge_execution.assert_not_called()


class TestPurgeBySession:
    def test_session_with_keys_soft_purges_each(self):
        metrics = create_autospec(MetricsPort)
        metrics.execution_keys_for_session.return_value = ["key1", "key2"]
        repo = create_autospec(ExecutionRepositoryPort)
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.purge_by_session(PurgeBySessionCommand("sess-1"))

        assert report.executions_removed == 2
        repo.soft_purge_execution.assert_any_call("key1")

    def test_session_with_no_keys_returns_empty_report(self):
        metrics = create_autospec(MetricsPort)
        metrics.execution_keys_for_session.return_value = []
        svc = _make_svc(metrics=metrics)

        report = svc.purge_by_session(PurgeBySessionCommand("empty-sess"))

        assert report.executions_removed == 0
        # no soft_purge assertion: _soft_purge_keys short-circuits on an empty session


class TestPurgeBySessionTag:
    def test_fans_out_through_sessions(self):
        metrics = create_autospec(MetricsPort)
        metrics.session_ids_for_tag.return_value = ["sess-A", "sess-B"]
        metrics.execution_keys_for_session.side_effect = [["key1"], ["key2"]]
        repo = create_autospec(ExecutionRepositoryPort)
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.purge_by_session_tag(PurgeBySessionTagCommand("my-tag"))

        assert report.executions_removed == 2
        repo.soft_purge_execution.assert_any_call("key1")
        repo.soft_purge_execution.assert_any_call("key2")

    def test_deduplicates_keys_across_sessions(self):
        metrics = create_autospec(MetricsPort)
        metrics.session_ids_for_tag.return_value = ["sess-A", "sess-B"]
        metrics.execution_keys_for_session.side_effect = [["key1"], ["key1"]]
        repo = create_autospec(ExecutionRepositoryPort)
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.purge_by_session_tag(PurgeBySessionTagCommand("my-tag"))

        assert report.executions_removed == 1
        assert repo.soft_purge_execution.call_count == 1

    def test_no_sessions_returns_empty_report(self):
        metrics = create_autospec(MetricsPort)
        metrics.session_ids_for_tag.return_value = []
        svc = _make_svc(metrics=metrics)

        report = svc.purge_by_session_tag(PurgeBySessionTagCommand("unknown-tag"))

        assert report.executions_removed == 0


class TestPurgeAll:
    def test_purges_all_current_executions(self):
        entries = [
            ExecutionSizeEntry("key1", 100, "2026-01-01T00:00:00"),
            ExecutionSizeEntry("key2", 200, "2026-01-01T00:00:00"),
        ]
        repo = create_autospec(ExecutionRepositoryPort)
        repo.current_executions_with_sizes.return_value = entries
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        svc = _make_svc(repo=repo)

        report = svc.purge_all(PurgeAllCommand())

        assert report.executions_removed == 2
        repo.soft_purge_execution.assert_any_call("key1")
        repo.soft_purge_execution.assert_any_call("key2")

    def test_empty_store_returns_empty_report(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.current_executions_with_sizes.return_value = []
        svc = _make_svc(repo=repo)

        report = svc.purge_all(PurgeAllCommand())

        assert report.executions_removed == 0
        repo.soft_purge_execution.assert_not_called()


class TestHardDeleteOne:
    def test_key_exists_calls_hard_delete_and_delete_events(self):
        repo = _repo_with_key()
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, metrics=metrics)

        svc.purge_by_key(PurgeByKeyCommand("key1", hard=True))

        repo.hard_delete_execution.assert_called_once_with("key1")
        metrics.delete_events_for_key.assert_called_once_with("key1")

    def test_key_exists_report_has_executions_removed_1(self):
        repo = _repo_with_key()
        svc = _make_svc(repo=repo)

        report = svc.purge_by_key(PurgeByKeyCommand("key1", hard=True))

        assert report.executions_removed == 1

    def test_key_not_found_returns_empty_report(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_all.return_value = []
        svc = _make_svc(repo=repo)

        report = svc.purge_by_key(PurgeByKeyCommand("missing", hard=True))

        assert report.executions_removed == 0

    def test_key_not_found_does_not_call_hard_delete_or_delete_events(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_all.return_value = []
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, metrics=metrics)

        svc.purge_by_key(PurgeByKeyCommand("missing", hard=True))

        repo.hard_delete_execution.assert_not_called()
        metrics.delete_events_for_key.assert_not_called()


class TestHardDeleteByTag:
    def test_hard_deletes_and_erases_events_for_each_tagged_key(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.executions_by_tag.return_value = ["key1", "key2"]
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.purge_by_tag(PurgeByTagCommand("my-tag", hard=True))

        assert report.executions_removed == 2
        repo.hard_delete_execution.assert_any_call("key1")
        metrics.delete_events_for_key.assert_any_call("key2")

    def test_empty_tag_returns_empty_report(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.executions_by_tag.return_value = []
        svc = _make_svc(repo=repo)

        report = svc.purge_by_tag(PurgeByTagCommand("empty-tag", hard=True))

        assert report.executions_removed == 0


class TestHardDeleteBySession:
    def test_hard_deletes_each_session_key_and_erases_events(self):
        metrics = create_autospec(MetricsPort)
        metrics.execution_keys_for_session.return_value = ["key1"]
        repo = create_autospec(ExecutionRepositoryPort)
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.purge_by_session(PurgeBySessionCommand("sess-1", hard=True))

        assert report.executions_removed == 1
        repo.hard_delete_execution.assert_called_once_with("key1")
        metrics.delete_events_for_key.assert_called_once_with("key1")


class TestHardDeleteAll:
    def test_hard_deletes_all_keys_and_erases_events(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.all_execution_keys.return_value = ["key1", "key2"]
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.purge_all(PurgeAllCommand(hard=True))

        assert report.executions_removed == 2
        repo.hard_delete_execution.assert_any_call("key1")
        metrics.delete_events_for_key.assert_any_call("key2")


class TestEvictStale:
    def test_zero_max_age_returns_empty_report_immediately(self):
        repo = create_autospec(ExecutionRepositoryPort)
        svc = _make_svc(repo=repo)

        report = svc.evict_stale(EvictStaleCommand(0))

        assert report.executions_removed == 0
        repo.current_executions_with_sizes.assert_not_called()

    def test_negative_max_age_returns_empty_report_immediately(self):
        repo = create_autospec(ExecutionRepositoryPort)
        svc = _make_svc(repo=repo)

        report = svc.evict_stale(EvictStaleCommand(-5))

        assert report.executions_removed == 0
        repo.current_executions_with_sizes.assert_not_called()

    def test_entry_past_cutoff_is_evicted(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.current_executions_with_sizes.return_value = [
            ExecutionSizeEntry("stale-key", 100, "2000-01-01T00:00:00"),
        ]
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        metrics = create_autospec(MetricsPort)
        metrics.last_access.return_value = {"stale-key": 0.0}
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.evict_stale(EvictStaleCommand(1))

        assert report.executions_removed == 1
        repo.soft_purge_execution.assert_called_once_with("stale-key")

    def test_entry_within_age_is_not_evicted(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.current_executions_with_sizes.return_value = [
            ExecutionSizeEntry("fresh-key", 100, "2026-01-01T00:00:00"),
        ]
        metrics = create_autospec(MetricsPort)
        metrics.last_access.return_value = {"fresh-key": time.time()}
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.evict_stale(EvictStaleCommand(1))

        assert report.executions_removed == 0
        repo.soft_purge_execution.assert_not_called()

    def test_lru_falls_back_to_created_at_when_key_absent_from_last_access(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.current_executions_with_sizes.return_value = [
            ExecutionSizeEntry("old-key", 100, "2000-01-01T00:00:00"),
        ]
        repo.blob_keys_for_execution.return_value = []
        repo.total_stored_bytes.return_value = 0
        metrics = create_autospec(MetricsPort)
        metrics.last_access.return_value = {}
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.evict_stale(EvictStaleCommand(1))

        assert report.executions_removed == 1


class TestEvictToQuota:
    def test_under_quota_returns_empty_report(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.total_stored_bytes.return_value = 100
        svc = _make_svc(repo=repo)

        report = svc.evict_to_quota(EvictToQuotaCommand(500))

        assert report.executions_removed == 0
        repo.current_executions_with_sizes.assert_not_called()

    def test_at_quota_returns_empty_report(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.total_stored_bytes.return_value = 500
        svc = _make_svc(repo=repo)

        report = svc.evict_to_quota(EvictToQuotaCommand(500))

        assert report.executions_removed == 0

    def test_over_quota_evicts_lru_entry_first(self):
        entries = [
            ExecutionSizeEntry("oldest", 600, "2025-01-01T00:00:00"),
            ExecutionSizeEntry("newest", 600, "2026-01-01T00:00:00"),
        ]
        repo = create_autospec(ExecutionRepositoryPort)
        repo.total_stored_bytes.side_effect = [1200, 0, 0]
        repo.current_executions_with_sizes.return_value = entries
        repo.blob_keys_for_execution.return_value = []
        metrics = create_autospec(MetricsPort)
        metrics.last_access.return_value = {"oldest": 1000.0, "newest": time.time()}
        svc = _make_svc(repo=repo, metrics=metrics)

        report = svc.evict_to_quota(EvictToQuotaCommand(700))

        assert report.executions_removed == 1
        repo.soft_purge_execution.assert_called_once_with("oldest")

    def test_blobs_with_zero_references_are_removed_from_blob_store(self):
        entries = [ExecutionSizeEntry("key1", 100, "2020-01-01T00:00:00")]
        blob = create_autospec(BlobStorePort)
        repo = create_autospec(ExecutionRepositoryPort)
        repo.total_stored_bytes.side_effect = [1000, 0, 0]
        repo.current_executions_with_sizes.return_value = entries
        repo.blob_keys_for_execution.return_value = ["blob-orphan"]
        repo.blob_reference_count.return_value = 0
        metrics = create_autospec(MetricsPort)
        metrics.last_access.return_value = {"key1": 0.0}
        svc = _make_svc(repo=repo, blob=blob, metrics=metrics)

        svc.evict_to_quota(EvictToQuotaCommand(500))

        blob.remove.assert_called_once_with("blob-orphan")

    def test_blobs_still_referenced_are_not_removed_from_blob_store(self):
        entries = [ExecutionSizeEntry("key1", 100, "2020-01-01T00:00:00")]
        blob = create_autospec(BlobStorePort)
        repo = create_autospec(ExecutionRepositoryPort)
        repo.total_stored_bytes.side_effect = [1000, 0, 0]
        repo.current_executions_with_sizes.return_value = entries
        repo.blob_keys_for_execution.return_value = ["blob-shared"]
        repo.blob_reference_count.return_value = 2
        metrics = create_autospec(MetricsPort)
        metrics.last_access.return_value = {"key1": 0.0}
        svc = _make_svc(repo=repo, blob=blob, metrics=metrics)

        svc.evict_to_quota(EvictToQuotaCommand(500))

        blob.remove.assert_not_called()
