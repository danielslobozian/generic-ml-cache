# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from unittest.mock import MagicMock, create_autospec

import pytest

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.call_journal_ports import RecordCallEventPort
from generic_ml_cache_core.application.port.outbound.execution_key_lock_port import (
    ExecutionKeyLockPort,
)
from generic_ml_cache_core.application.port.outbound.ml_run_ports import (
    AnnotateMlRunPort,
    ReadMlRunPort,
    SaveMlRunPort,
)
from generic_ml_cache_core.application.port.outbound.store_lock_port import StoreLockPort
from generic_ml_cache_core.application.usecase.cached_ml_execution_service import (
    CachedMlExecutionService,
)
from generic_ml_cache_core.common.errors import (
    CacheMiss,
    EncryptionTokenRequired,
    StoreUnavailable,
)
from generic_ml_cache_core.testing.in_process_execution_key_lock import (
    InProcessExecutionKeyLock,
)

# ---------------------------------------------------------------------------
# Minimal concrete subclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _StubIdentity(CallIdentity):
    """A fixed identity for exercising the shared base — the key is verbatim."""

    cache_key: str = "test-key"

    def generate_key(self) -> str:
        return self.cache_key

    @property
    def summary_client(self) -> str:
        return "test-client"

    @property
    def summary_model(self) -> str:
        return "test-model"


class _MlRunStore(SaveMlRunPort, ReadMlRunPort, AnnotateMlRunPort): ...


class _RunSvc(CachedMlExecutionService):
    def __init__(self, blob, repo, metrics, runner=None, **kw):
        kw.setdefault("execution_key_lock", InProcessExecutionKeyLock())
        super().__init__(blob, save=repo, read=repo, annotate=repo, record=metrics, **kw)
        self._runner = runner or MagicMock()

    def _build_identity(self, cmd):
        return _StubIdentity()

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
        call_identity=_StubIdentity(),
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        artifacts=[artifact],
    )


def _make_svc(blob=None, repo=None, metrics=None, runner=None):
    return _RunSvc(
        blob=blob or create_autospec(BlobStorePort),
        repo=repo or create_autospec(_MlRunStore),
        metrics=metrics or create_autospec(RecordCallEventPort),
        runner=runner,
    )


# ---------------------------------------------------------------------------
# Stateful write-path fakes (Y17): unlike the autospec mocks above, these hold
# real state so a test can assert the DURABLE outcome (artifact status, blob
# presence, finalize) of a partial failure — which a call-count mock cannot.
# ---------------------------------------------------------------------------


class _StatefulBlobStore(BlobStorePort):
    """An in-memory blob store that really stores bytes; can fail every write/remove."""

    def __init__(self, fail_all_puts: bool = False, fail_all_removes: bool = False):
        self.blobs: dict[str, bytes] = {}
        self._fail_all_puts = fail_all_puts
        self._fail_all_removes = fail_all_removes

    def get(self, key):
        return self.blobs.get(str(key))

    def put(self, key, output):
        if self._fail_all_puts:
            raise StoreUnavailable(f"injected blob write failure for {key!r}")
        self.blobs[str(key)] = output

    def is_healthy(self):
        return True

    def remove(self, key):
        if self._fail_all_removes:
            raise StoreUnavailable(f"injected blob remove failure for {key!r}")
        self.blobs.pop(str(key), None)


class _StatefulWriteStore(_MlRunStore):
    """A stateful persistence fake for the write path: tracks artifact status per
    (execution_id, blob_key) and can inject a mark-STORED DB failure (Y6)."""

    def __init__(self, fail_mark_stored: bool = False):
        self.executions: dict[str, MlExecution] = {}
        self.artifact_status: dict[tuple[str, str], ArtifactStatus] = {}
        self.finalized: set[str] = set()
        self.mark_failed_calls: list[tuple[str, str]] = []
        self.removed_executions: list[str] = []
        self._fail_mark_stored = fail_mark_stored

    def save(self, execution):
        self.executions[execution.execution_id] = execution

    def record_outcome(self, execution):
        self.executions[execution.execution_id] = execution

    def persist_artifact(self, execution_id, artifact):
        self.artifact_status[(execution_id, str(artifact.blob_key))] = ArtifactStatus.PENDING

    def remove_execution(self, execution_id):
        self.removed_executions.append(execution_id)
        self.executions.pop(execution_id, None)

    def mark_artifacts_stored(self, execution_id, blob_key):
        if self._fail_mark_stored:
            raise StoreUnavailable("injected DB mark failure")
        self.artifact_status[(execution_id, str(blob_key))] = ArtifactStatus.STORED

    def mark_artifacts_failed(self, execution_id, blob_key, detail):
        self.mark_failed_calls.append((execution_id, str(blob_key)))
        self.artifact_status[(execution_id, str(blob_key))] = ArtifactStatus.FAILED

    def finalize_output_persisted(self, execution_id):
        self.finalized.add(execution_id)

    def find_current(self, execution_key):
        return None

    def add_tags(self, execution_key, tags):
        pass

    def add_input_artifacts(self, execution_key, artifacts):
        pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCacheMode:
    def test_hit_returns_hydrated_execution_without_calling_client(self):
        runner = MagicMock()
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = _make_execution()
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = b"data"
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        result = svc.execute(_Cmd())

        assert result.output_persisted is True
        runner.assert_not_called()

    def test_hit_records_hit_event(self):
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = _make_execution()
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = b"data"
        metrics = create_autospec(RecordCallEventPort)
        svc = _make_svc(repo=repo, blob=blob, metrics=metrics)

        svc.execute(_Cmd())

        assert metrics.record_event.call_args[0][0] == "hit"

    def test_miss_runs_client_and_saves_in_progress_then_final(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd())

        runner.assert_called_once()
        # One row: save inserts IN_PROGRESS, record_outcome transitions it (W1).
        assert repo.save.call_count == 1
        assert repo.record_outcome.call_count == 1

    def test_miss_records_record_event(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        metrics = create_autospec(RecordCallEventPort)
        svc = _make_svc(repo=repo, metrics=metrics, runner=runner)

        svc.execute(_Cmd())

        assert metrics.record_event.call_args[0][0] == "record"

    def test_miss_stores_output_blobs(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        blob = create_autospec(BlobStorePort)
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        svc.execute(_Cmd())

        assert blob.put.call_count >= 1


class TestRefreshMode:
    def test_runs_client_without_checking_cache(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(cache_mode=CacheMode.REFRESH))

        runner.assert_called_once()
        repo.find_current.assert_not_called()

    def test_saves_in_progress_then_final(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(cache_mode=CacheMode.REFRESH))

        # One row: save inserts IN_PROGRESS, record_outcome transitions it (W1).
        assert repo.save.call_count == 1
        assert repo.record_outcome.call_count == 1


class TestOfflineMode:
    def test_serves_cached_execution_without_calling_client(self):
        runner = MagicMock()
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = _make_execution()
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = b"data"
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        result = svc.execute(_Cmd(cache_mode=CacheMode.OFFLINE))

        assert result.output_persisted is True
        runner.assert_not_called()

    def test_raises_cache_miss_when_no_stored_execution(self):
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo)

        with pytest.raises(CacheMiss):
            svc.execute(_Cmd(cache_mode=CacheMode.OFFLINE))


class TestMeterDepth:
    def test_always_runs_client(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        runner.assert_called_once()

    def test_never_saves_to_repository(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        repo.save.assert_not_called()

    def test_journals_would_hit_when_stored_entry_exists(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = _make_execution()
        metrics = create_autospec(RecordCallEventPort)
        svc = _make_svc(repo=repo, metrics=metrics, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        assert metrics.record_event.call_args[0][0] == "would_hit"

    def test_journals_would_miss_when_no_stored_entry(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        metrics = create_autospec(RecordCallEventPort)
        svc = _make_svc(repo=repo, metrics=metrics, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        assert metrics.record_event.call_args[0][0] == "would_miss"


class TestUncacheable:
    def test_cache_mode_runs_client_without_saving(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        svc = _make_svc(repo=repo, runner=runner)

        svc.execute(_Cmd(_is_uncacheable=True))

        runner.assert_called_once()
        repo.save.assert_not_called()

    def test_cache_mode_records_run_event(self):
        runner = MagicMock(return_value=_make_result())
        metrics = create_autospec(RecordCallEventPort)
        svc = _make_svc(metrics=metrics, runner=runner)

        svc.execute(_Cmd(_is_uncacheable=True))

        assert metrics.record_event.call_args[0][0] == "run"

    def test_offline_mode_raises_cache_miss_without_calling_client(self):
        runner = MagicMock()
        svc = _make_svc(runner=runner)

        with pytest.raises(CacheMiss):
            svc.execute(_Cmd(cache_mode=CacheMode.OFFLINE, _is_uncacheable=True))

        runner.assert_not_called()


class TestCorruptCassette:
    def test_offline_missing_blob_degrades_to_cache_miss(self):
        # A would-be hit whose blob is gone is a corrupt cassette. OFFLINE cannot
        # re-run to self-heal, so it is a clean CacheMiss, not a crash (S4).
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = _make_execution(blob_key="blob-gone")
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = None
        svc = _make_svc(repo=repo, blob=blob)

        with pytest.raises(CacheMiss):
            svc.execute(_Cmd(cache_mode=CacheMode.OFFLINE))


class TestFailedRun:
    def test_failed_run_resolves_in_progress_but_does_not_store_blobs(self):
        runner = MagicMock(return_value=ClientRunResult(exit_code=1))
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        blob = create_autospec(BlobStorePort)
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        svc.execute(_Cmd())

        # save inserts IN_PROGRESS, record_outcome transitions it to FAILED; no blobs.
        assert repo.save.call_count == 1
        assert repo.record_outcome.call_count == 1
        blob.put.assert_not_called()

    def test_failed_run_records_run_not_record_event(self):
        runner = MagicMock(return_value=ClientRunResult(exit_code=1))
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        metrics = create_autospec(RecordCallEventPort)
        svc = _make_svc(repo=repo, metrics=metrics, runner=runner)

        svc.execute(_Cmd())

        assert metrics.record_event.call_args[0][0] == "run"


class TestAfterRecord:
    def test_after_record_called_once_on_successful_store(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        svc = _AfterRecordSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(RecordCallEventPort),
            runner=runner,
        )

        svc.execute(_Cmd())

        assert svc.after_record_calls == ["test-key"]

    def test_after_record_not_called_when_run_fails(self):
        runner = MagicMock(return_value=ClientRunResult(exit_code=1))
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        svc = _AfterRecordSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(RecordCallEventPort),
            runner=runner,
        )

        svc.execute(_Cmd())

        assert svc.after_record_calls == []


class TestTags:
    def test_add_tags_called_after_successful_record(self):
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        svc = _TagSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(RecordCallEventPort),
            runner=runner,
        )

        svc.execute(_Cmd())

        repo.add_tags.assert_called_once_with("test-key", ["tag1"])

    def test_add_tags_not_called_when_run_fails(self):
        runner = MagicMock(return_value=ClientRunResult(exit_code=1))
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        svc = _TagSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(RecordCallEventPort),
            runner=runner,
        )

        svc.execute(_Cmd())

        repo.add_tags.assert_not_called()

    def test_add_tags_called_on_cache_hit(self):
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = _make_execution()
        blob = create_autospec(BlobStorePort)
        blob.get.return_value = b"data"
        svc = _TagSvc(
            blob=blob,
            repo=repo,
            metrics=create_autospec(RecordCallEventPort),
        )

        svc.execute(_Cmd())

        repo.add_tags.assert_called_once_with("test-key", ["tag1"])


class _SpyKeyLock(ExecutionKeyLockPort):
    """Records which keys the record-once critical section is entered under (X7)."""

    def __init__(self) -> None:
        self.acquired: list[str] = []

    @contextmanager
    def acquire(self, execution_key: str):
        self.acquired.append(execution_key)
        yield


class TestExecutionKeyLock:
    def test_a_fresh_run_is_guarded_by_the_injected_per_key_lock(self):
        # X7: a cache miss runs the client under the injected ExecutionKeyLock, keyed
        # by the execution key — the seam that now spans processes, not just threads.
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        spy = _SpyKeyLock()
        svc = _RunSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(RecordCallEventPort),
            runner=runner,
            execution_key_lock=spy,
        )

        svc.execute(_Cmd())

        assert spy.acquired == ["test-key"]  # the miss ran under the per-key lock


class _SpyStoreLock(StoreLockPort):
    """Records shared vs exclusive store-lock acquisitions (X8)."""

    def __init__(self) -> None:
        self.shared_acquisitions = 0
        self.exclusive_acquisitions = 0

    @contextmanager
    def acquire(self):
        self.exclusive_acquisitions += 1
        yield

    @contextmanager
    def acquire_shared(self):
        self.shared_acquisitions += 1
        yield


class TestStoreLock:
    def test_a_content_write_holds_the_store_lock_shared(self):
        # X8: writing the output blobs on a miss takes the store lock SHARED (never
        # exclusive), so concurrent writes coexist but a migration excludes them all.
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        store_lock = _SpyStoreLock()
        svc = _RunSvc(
            blob=create_autospec(BlobStorePort),
            repo=repo,
            metrics=create_autospec(RecordCallEventPort),
            runner=runner,
            execution_key_lock=InProcessExecutionKeyLock(),
            store_lock=store_lock,
        )

        svc.execute(_Cmd())

        assert store_lock.shared_acquisitions >= 1
        assert store_lock.exclusive_acquisitions == 0


class TestStoreUnavailable:
    def test_dead_store_fails_loud_without_invoking_the_client(self):
        # S2b: if the database is a hard outage, the first repo read raises
        # StoreUnavailable and the expensive client is never called.
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.side_effect = StoreUnavailable("cache database is unavailable")
        svc = _make_svc(repo=repo, runner=runner)

        with pytest.raises(StoreUnavailable):
            svc.execute(_Cmd())

        runner.assert_not_called()


class TestDatasetFailFast:
    def test_dataset_run_fails_fast_when_blob_store_is_unhealthy(self):
        # S1.1: at DATASET depth, persisting input+output is the point — so an
        # unhealthy blob store fails fast BEFORE the expensive client call.
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        blob = create_autospec(BlobStorePort)
        blob.is_healthy.return_value = False
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        with pytest.raises(StoreUnavailable):
            svc.execute(_Cmd(persistence_depth=PersistenceDepth.DATASET))

        runner.assert_not_called()

    def test_cache_run_proceeds_even_when_blob_store_is_unhealthy(self):
        # S1.2: CACHE is best-effort — the answer is still returned, so an unhealthy
        # store does not gate the client call (only persistence is best-effort).
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        blob = create_autospec(BlobStorePort)
        blob.is_healthy.return_value = False
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.CACHE))

        runner.assert_called_once()


class TestEncryptionTokenGate:
    def test_content_op_without_token_fails_before_the_client(self):
        # S5a: an encrypted store with no token fails the gate up front — the
        # expensive client is never called.
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        blob = create_autospec(BlobStorePort)
        blob.ensure_available_for_content.side_effect = EncryptionTokenRequired("need token")
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        with pytest.raises(EncryptionTokenRequired):
            svc.execute(_Cmd())  # CACHE depth stores output → gated

        runner.assert_not_called()

    def test_meter_depth_skips_the_token_gate(self):
        # A DB-only METER run touches no blob, so the token gate is never consulted.
        runner = MagicMock(return_value=_make_result())
        repo = create_autospec(_MlRunStore)
        repo.find_current.return_value = None
        blob = create_autospec(BlobStorePort)
        blob.ensure_available_for_content.side_effect = EncryptionTokenRequired("need token")
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        svc.execute(_Cmd(persistence_depth=PersistenceDepth.METER))

        runner.assert_called_once()
        blob.ensure_available_for_content.assert_not_called()


class TestStoreBlobPhaseSplit:
    """Y6: blob-write and DB-mark are SEPARATE phases, asserted on durable state."""

    def test_db_mark_failure_leaves_pending_not_failed_and_returns_the_result(self):
        # The blob lands (phase 1 ok) but the DB mark fails (phase 2): the artifact must
        # stay PENDING (repairable), never FAILED; no second DB write is fired against
        # the failing DB; the run is not finalized; and the caller still gets the answer.
        runner = MagicMock(return_value=_make_result())
        repo = _StatefulWriteStore(fail_mark_stored=True)
        blob = _StatefulBlobStore()
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        result = svc.execute(_Cmd())

        assert blob.blobs  # the blob really landed on the store
        assert ArtifactStatus.FAILED not in repo.artifact_status.values()  # never a lie
        assert ArtifactStatus.PENDING in repo.artifact_status.values()  # left for repair
        assert repo.mark_failed_calls == []  # NO second DB write on the failing DB
        assert repo.finalized == set()  # not servable
        assert result.output_persisted is False
        assert result.execution_state is ExecutionState.SUCCESS  # the good answer survives

    def test_blob_write_failure_marks_the_artifact_failed(self):
        # Phase 1 fails: the artifact IS marked FAILED (the DB is healthy, that mark
        # lands) and the run is not persisted — the unchanged pre-Y6 behaviour.
        runner = MagicMock(return_value=_make_result())
        repo = _StatefulWriteStore()
        blob = _StatefulBlobStore(fail_all_puts=True)
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        result = svc.execute(_Cmd())

        assert ArtifactStatus.FAILED in repo.artifact_status.values()
        assert repo.mark_failed_calls  # the failed mark WAS written (DB is fine)
        assert repo.finalized == set()
        assert result.output_persisted is False

    def test_all_phases_succeed_finalizes_and_stores(self):
        # The happy path through the stateful fakes: blob stored, artifact STORED, run
        # finalized, output_persisted True — the state-based mirror of the mock tests.
        runner = MagicMock(return_value=_make_result())
        repo = _StatefulWriteStore()
        blob = _StatefulBlobStore()
        svc = _make_svc(repo=repo, blob=blob, runner=runner)

        result = svc.execute(_Cmd())

        assert blob.blobs
        assert set(repo.artifact_status.values()) == {ArtifactStatus.STORED}
        assert repo.finalized  # finalize_output_persisted ran
        assert result.output_persisted is True


class TestSelfHealRemovalOrder:
    """Y7: self-heal deletes the blobs (the pointed-to bytes) BEFORE the rows (the
    pointer), so a blob-remove failure leaves a discoverable row, not an orphan."""

    def test_clean_self_heal_removes_both_blobs_and_rows(self):
        repo = _StatefulWriteStore()
        blob = _StatefulBlobStore()
        blob.blobs["blob-1"] = b"corrupt"
        svc = _make_svc(repo=repo, blob=blob)

        svc._remove_execution_and_blobs(_make_execution())

        assert "blob-1" not in blob.blobs  # the blob was removed
        assert repo.removed_executions  # and then the row

    def test_blob_remove_failure_leaves_the_row_intact_no_orphan(self):
        repo = _StatefulWriteStore()
        blob = _StatefulBlobStore(fail_all_removes=True)
        svc = _make_svc(repo=repo, blob=blob)

        with pytest.raises(StoreUnavailable):
            svc._remove_execution_and_blobs(_make_execution())

        # Blobs-first: the remove failed before the row delete ran, so the naming row
        # is intact and the blob is still discoverable for a later repair/purge — the
        # old rows-first order would have deleted the row and orphaned the blob.
        assert repo.removed_executions == []
