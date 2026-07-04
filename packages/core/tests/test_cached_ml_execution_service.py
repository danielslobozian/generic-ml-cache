# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, create_autospec

import pytest

from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact, ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.gateway_call_identity import (
    GatewayCallIdentity,
)
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.outbound.metrics_port import MetricsPort
from generic_ml_cache_core.application.usecase.cached_ml_execution_service import (
    CachedMlExecutionService,
)
from generic_ml_cache_core.common.errors import ArtifactBlobMissing, CacheMiss

# ---------------------------------------------------------------------------
# Minimal concrete subclass
# ---------------------------------------------------------------------------


class _RunSvc(CachedMlExecutionService):
    def __init__(self, blob, repo, metrics, runner=None, **kw):
        super().__init__(blob, repo, metrics, **kw)
        self._runner = runner or MagicMock()

    def _build_identity(self, cmd):
        return GatewayCallIdentity(cache_key="test-key")

    def _run_client(self, cmd):
        return self._runner(cmd)

    def _execution_kind(self, cmd):
        return ExecutionKind.LOCAL_MANAGED

    def _journal_fields(self, cmd):
        return ("test-client", "test-model", "low")

    def _is_uncacheable(self, cmd):
        return cmd._is_uncacheable


# Subclasses used in hook tests
class _AfterRecordSvc(_RunSvc):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.after_record_calls: list = []

    def _after_record(self, key):
        self.after_record_calls.append(key)


class _TagSvc(_RunSvc):
    def _execution_tags(self, cmd):
        return ["tag1"]


# ---------------------------------------------------------------------------
# Command stub
# ---------------------------------------------------------------------------


@dataclass
class _Cmd:
    cache_mode: CacheMode = CacheMode.CACHE
    persistence_depth: PersistenceDepth = PersistenceDepth.CACHE
    session_id: str | None = "sess-1"
    _is_uncacheable: bool = False
    _should_persist: bool = True

    def should_persist(self, succeeded: bool) -> bool:
        return self._should_persist and succeeded


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_result(exit_code: int = 0) -> ClientRunResult:
    return ClientRunResult(exit_code=exit_code, stdout="out", stderr="")


def _make_execution(blob_key: str = "blob-1") -> MlExecution:
    artifact = Artifact(
        artifact_type=ArtifactType.STDOUT,
        blob_key=blob_key,
        size_bytes=4,
    )
    return MlExecution(
        call_identity=GatewayCallIdentity(cache_key="test-key"),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        artifacts=[artifact],
    )


def _make_svc(blob=None, repo=None, metrics=None, runner=None):
    return _RunSvc(
        blob=blob or create_autospec(BlobStorePort),
        repo=repo or create_autospec(ExecutionRepositoryPort),
        metrics=metrics or create_autospec(MetricsPort),
        runner=runner,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCacheMode:
    def test_hit_returns_hydrated_execution_without_calling_client(self):
        runner = MagicMock()
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = _make_execution()
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = b"data"
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        result = svc.execute(_Cmd())

        assert result.output_persisted is True
        runner.assert_not_called()

    def test_hit_records_hit_event(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = _make_execution()
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = b"data"
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, blob=blob, metrics=metrics)

        svc.execute(_Cmd())

        assert metrics.record_event.call_args[0][0] == "hit"

    def test_miss_runs_client_and_saves_in_progress_then_final(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd())

        runner.assert_called_once()
        assert repo.save.call_count == 2

    def test_miss_records_record_event(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, metrics=metrics, runner=runner)

        svc.execute(_Cmd())

        assert metrics.record_event.call_args[0][0] == "record"

    def test_miss_stores_output_blobs(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        blob = create_autospec(BlobStorePort)
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        svc.execute(_Cmd())

        assert blob.put.call_count >= 1


class TestRefreshMode:
    def test_runs_client_without_checking_cache(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(cache_mode=CacheMode.REFRESH))

        runner.assert_called_once()
        repo.find_current.assert_not_called()

    def test_saves_in_progress_then_final(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(cache_mode=CacheMode.REFRESH))

        assert repo.save.call_count == 2


class TestOfflineMode:
    def test_serves_cached_execution_without_calling_client(self):
        runner = MagicMock()
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = _make_execution()
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = b"data"
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        result = svc.execute(_Cmd(cache_mode=CacheMode.OFFLINE))

        assert result.output_persisted is True
        runner.assert_not_called()

    def test_raises_cache_miss_when_no_stored_execution(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        with pytest.raises(CacheMiss):
            svc.execute(_Cmd(cache_mode=CacheMode.OFFLINE))


class TestMeterDepth:
    def test_always_runs_client(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        runner.assert_called_once()

    def test_never_saves_to_repository(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        repo.save.assert_not_called()

    def test_journals_would_hit_when_stored_entry_exists(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = _make_execution()
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, metrics=metrics, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        assert metrics.record_event.call_args[0][0] == "would_hit"

    def test_journals_would_miss_when_no_stored_entry(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, metrics=metrics, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        assert metrics.record_event.call_args[0][0] == "would_miss"


class TestUncacheable:
    def test_cache_mode_runs_client_without_saving(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(_is_uncacheable=True))

        runner.assert_called_once()
        repo.save.assert_not_called()

    def test_cache_mode_records_run_event(self):
        runner = MagicMock(return_value=_make_result())
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(metrics=metrics, runner=runner)

        svc.execute(_Cmd(_is_uncacheable=True))

        assert metrics.record_event.call_args[0][0] == "run"

    def test_offline_mode_raises_cache_miss_without_calling_client(self):
        runner = MagicMock()
        svc = _make_svc(runner=runner)

        with pytest.raises(CacheMiss):
            svc.execute(_Cmd(cache_mode=CacheMode.OFFLINE, _is_uncacheable=True))

        runner.assert_not_called()


class TestBlobMissing:
    def test_raises_artifact_blob_missing_when_get_returns_none(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = _make_execution(blob_key="blob-gone")
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = None
        svc = _make_svc(repo=repo, blob=blob)

        with pytest.raises(ArtifactBlobMissing):
            svc.execute(_Cmd())


class TestFailedRun:
    def test_failed_run_resolves_in_progress_but_does_not_store_blobs(self):
        runner = MagicMock(return_value=ClientRunResult(exit_code=1))
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        blob = create_autospec(BlobStorePort)
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        svc.execute(_Cmd())

        assert repo.save.call_count == 2
        blob.put.assert_not_called()

    def test_failed_run_records_run_not_record_event(self):
        runner = MagicMock(return_value=ClientRunResult(exit_code=1))
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        metrics = create_autospec(MetricsPort)
        svc = _make_svc(repo=repo, metrics=metrics, runner=runner)

        svc.execute(_Cmd())

        assert metrics.record_event.call_args[0][0] == "run"


class TestAfterRecord:
    def test_after_record_called_once_on_successful_store(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        svc = _AfterRecordSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(MetricsPort),
            runner=runner,
        )

        svc.execute(_Cmd())

        assert svc.after_record_calls == ["test-key"]

    def test_after_record_not_called_when_run_fails(self):
        runner = MagicMock(return_value=ClientRunResult(exit_code=1))
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        svc = _AfterRecordSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(MetricsPort),
            runner=runner,
        )

        svc.execute(_Cmd())

        assert svc.after_record_calls == []


class TestTags:
    def test_add_tags_called_after_successful_record(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        svc = _TagSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(MetricsPort),
            runner=runner,
        )

        svc.execute(_Cmd())

        repo.add_tags.assert_called_once_with("test-key", ["tag1"])

    def test_add_tags_not_called_when_run_fails(self):
        runner = MagicMock(return_value=ClientRunResult(exit_code=1))
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = None
        svc = _TagSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(MetricsPort),
            runner=runner,
        )

        svc.execute(_Cmd())

        repo.add_tags.assert_not_called()

    def test_add_tags_called_on_cache_hit(self):
        repo = create_autospec(ExecutionRepositoryPort)
        repo.find_current.return_value = _make_execution()
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = b"data"
        svc = _TagSvc(
            blob=blob,
            repo=repo,
            metrics=create_autospec(MetricsPort),
        )

        svc.execute(_Cmd())

        repo.add_tags.assert_called_once_with("test-key", ["tag1"])
