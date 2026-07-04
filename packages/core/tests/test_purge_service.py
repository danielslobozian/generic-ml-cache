# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for PurgeService."""

from __future__ import annotations

import time as _time_module
from datetime import datetime, timezone

from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact, ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.session.session_event_row import (
    SessionEventRow,
)
from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
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
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.call_journal_ports import (
    CallStatsPort,
    PurgeJournalPort,
    RecordCallEventPort,
    SessionQueryPort,
    SessionReportSourcePort,
    SessionSpecPort,
    SessionTagsPort,
)
from generic_ml_cache_core.application.port.outbound.clock_port import ClockPort
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.testing.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)

_MOMENT = datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return _MOMENT


class InMemoryBlobStore(BlobStorePort):
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    def put(self, key: str, output: bytes) -> None:
        self._store[key] = output

    def is_healthy(self) -> bool:
        return True

    def remove(self, key: str) -> None:
        self._store.pop(key, None)

    def has(self, key: str) -> bool:
        return key in self._store


class FakeMetrics(
    RecordCallEventPort,
    CallStatsPort,
    SessionReportSourcePort,
    SessionQueryPort,
    PurgeJournalPort,
    SessionTagsPort,
    SessionSpecPort,
):
    """Controllable fake for PurgeService tests."""

    def __init__(
        self,
        last_access: dict[str, float] | None = None,
        session_keys: dict[str, list[str]] | None = None,
    ) -> None:
        self._last_access = last_access or {}
        self._session_keys = session_keys or {}
        self._deleted_keys: list[str] = []
        self._session_tags_index: dict[str, list[str]] = {}

    def record_event(self, event, *, execution_key, client, model, effort, session_id=None):
        pass

    def hit_counts_by_key(self) -> dict[str, int]:
        return {}

    def event_counts(self) -> dict[str, int]:
        return {}

    def session_event_counts(self, session_id: str) -> dict[str, int]:
        return {}

    def session_events(self, session_id: str) -> list[SessionEventRow]:
        return []

    def last_access(self) -> dict[str, float]:
        return self._last_access

    def execution_keys_for_session(self, session_id: str) -> list[str]:
        return self._session_keys.get(session_id, [])

    def delete_events_for_key(self, execution_key: str) -> None:
        self._deleted_keys.append(execution_key)

    def add_session_tag(self, session_id: str, tag: str) -> None:
        pass

    def remove_session_tag(self, session_id: str, tag: str) -> None:
        pass

    def set_session_spec(self, session_id: str, spec: SessionSpec) -> None:
        pass

    def clear_session_spec(self, session_id: str) -> None:
        pass

    def session_spec(self, session_id: str) -> SessionSpec | None:
        return None

    def list_session_ids(self) -> list[str]:
        return []

    def session_tags(self, session_id: str) -> list[str]:
        return []

    def session_ids_for_tag(self, tag: str) -> list[str]:
        return self._session_tags_index.get(tag, [])

    def _with_session_tags(self, tag_to_sessions: dict[str, list[str]]) -> FakeMetrics:
        self._session_tags_index = tag_to_sessions
        return self


def _identity(prompt: str = "p") -> ManagedCallIdentity:
    return ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="c",
        prompt_fingerprint=prompt,
    )


def _execution(identity, content: bytes = b"answer", token_usage=None) -> MlExecution:
    artifact = Artifact(
        artifact_type=ArtifactType.STDOUT,
        blob_key="blob_" + content.hex(),
        size_bytes=len(content),
        content=content,
    )
    return MlExecution(
        call_identity=identity,
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        artifacts=[artifact],
        token_usage=token_usage,
    )


def _service(repository=None, blob_store=None, metrics=None):
    repo = repository or InMemoryExecutionRepository(FixedClock())
    store = blob_store or InMemoryBlobStore()
    met = metrics or FakeMetrics()
    return PurgeService(repo, store, met, met), repo, store, met


# --- soft purge: purge_one ---------------------------------------------------


def test_purge_one_frees_bytes_and_reports_correctly():
    svc, repo, store, _ = _service()
    identity = _identity()
    repo.save(_execution(identity, content=b"answer"))
    store.put("blob_" + b"answer".hex(), b"answer")
    key = identity.generate_key()

    report = svc.purge_by_key(PurgeByKeyCommand(key))

    assert report.executions_removed == 1
    assert report.bytes_freed == len(b"answer")
    assert report.blobs_removed == 1


def test_purge_one_deletes_blob_from_store():
    svc, repo, store, _ = _service()
    identity = _identity()
    blob_key = "blob_" + b"answer".hex()
    repo.save(_execution(identity, content=b"answer"))
    store.put(blob_key, b"answer")

    svc.purge_by_key(PurgeByKeyCommand(identity.generate_key()))

    assert not store.has(blob_key)


def test_purge_one_makes_execution_not_servable():
    svc, repo, _, _ = _service()
    identity = _identity()
    repo.save(_execution(identity))
    key = identity.generate_key()
    svc.purge_by_key(PurgeByKeyCommand(key))
    assert repo.find_current(key) is None


def test_purge_one_preserves_token_usage():
    svc, repo, _, _ = _service()
    identity = _identity()
    usage = TokenUsage(input_tokens=10, output_tokens=5, raw={"x": 1})
    repo.save(_execution(identity, token_usage=usage))
    svc.purge_by_key(PurgeByKeyCommand(identity.generate_key()))
    history = repo.find_all(identity.generate_key())
    assert history[0].token_usage == usage


def test_purge_one_unknown_key_returns_empty_report():
    svc, _, _, _ = _service()
    report = svc.purge_by_key(PurgeByKeyCommand("nope"))
    assert report.executions_removed == 0
    assert report.bytes_freed == 0
    assert report.blobs_removed == 0


# --- soft purge: purge_by_tag ------------------------------------------------


def test_purge_by_tag_purges_matching_executions():
    svc, repo, store, _ = _service()
    id_a = _identity("a")
    id_b = _identity("b")
    repo.save(_execution(id_a, content=b"aaa"))
    repo.save(_execution(id_b, content=b"bb"))
    store.put("blob_" + b"aaa".hex(), b"aaa")
    store.put("blob_" + b"bb".hex(), b"bb")
    repo.add_tags(id_a.generate_key(), ["work"])

    report = svc.purge_by_tag(PurgeByTagCommand("work"))

    assert report.executions_removed == 1
    assert report.bytes_freed == 3
    assert not store.has("blob_" + b"aaa".hex())
    assert store.has("blob_" + b"bb".hex())  # untagged — untouched


def test_purge_by_tag_unknown_tag_returns_empty_report():
    svc, _, _, _ = _service()
    report = svc.purge_by_tag(PurgeByTagCommand("nope"))
    assert report.executions_removed == 0
    assert report.bytes_freed == 0


# --- soft purge: purge_by_session --------------------------------------------


def test_purge_by_session_purges_matching_executions():
    id_a = _identity("a")
    id_b = _identity("b")
    repo = InMemoryExecutionRepository(FixedClock())
    store = InMemoryBlobStore()
    metrics = FakeMetrics(session_keys={"sess-1": [id_a.generate_key()]})
    svc = PurgeService(repo, store, metrics, metrics)

    repo.save(_execution(id_a, content=b"aaa"))
    repo.save(_execution(id_b, content=b"bb"))
    store.put("blob_" + b"aaa".hex(), b"aaa")
    store.put("blob_" + b"bb".hex(), b"bb")

    report = svc.purge_by_session(PurgeBySessionCommand("sess-1"))

    assert report.executions_removed == 1
    assert not store.has("blob_" + b"aaa".hex())
    assert store.has("blob_" + b"bb".hex())


def test_purge_by_session_unknown_session_returns_empty_report():
    svc, _, _, _ = _service()
    report = svc.purge_by_session(PurgeBySessionCommand("no-such-session"))
    assert report.executions_removed == 0


# --- soft purge: purge_all ---------------------------------------------------


def test_purge_all_purges_every_current_execution():
    svc, repo, store, _ = _service()
    for i in range(3):
        identity = _identity(str(i))
        content = f"content{i}".encode()
        repo.save(_execution(identity, content=content))
        store.put("blob_" + content.hex(), content)

    report = svc.purge_all(PurgeAllCommand())

    assert report.executions_removed == 3
    assert report.bytes_freed > 0
    assert report.blobs_removed == 3


def test_purge_all_empty_store_returns_zero_report():
    svc, _, _, _ = _service()
    report = svc.purge_all(PurgeAllCommand())
    assert report.executions_removed == 0
    assert report.bytes_freed == 0
    assert report.blobs_removed == 0


def test_bytes_freed_counts_a_shared_blob_once():
    # Two executions with distinct identities but identical content share one
    # content-addressed blob. The old before/after total summed size_bytes per
    # artifact, double-counting the shared blob; measuring the removed blobs
    # directly frees its size exactly once.
    svc, repo, store, _ = _service()
    shared_content = b"shared-answer"
    shared_blob_key = "blob_" + shared_content.hex()
    repo.save(_execution(_identity("a"), content=shared_content))
    repo.save(_execution(_identity("b"), content=shared_content))
    store.put(shared_blob_key, shared_content)

    report = svc.purge_all(PurgeAllCommand())

    assert report.executions_removed == 2
    assert report.blobs_removed == 1
    assert report.bytes_freed == len(shared_content)
    assert not store.has(shared_blob_key)


# --- hard delete: hard_delete_one --------------------------------------------


def test_hard_delete_one_removes_all_db_rows():
    svc, repo, store, _ = _service()
    identity = _identity()
    repo.save(_execution(identity))
    key = identity.generate_key()

    svc.purge_by_key(PurgeByKeyCommand(key, hard=True))

    assert repo.find_current(key) is None
    assert repo.find_all(key) == []


def test_hard_delete_one_deletes_blob():
    svc, repo, store, _ = _service()
    identity = _identity()
    blob_key = "blob_" + b"answer".hex()
    repo.save(_execution(identity, content=b"answer"))
    store.put(blob_key, b"answer")

    svc.purge_by_key(PurgeByKeyCommand(identity.generate_key(), hard=True))

    assert not store.has(blob_key)


def test_hard_delete_one_records_event_deletion():
    svc, repo, store, metrics = _service()
    identity = _identity()
    repo.save(_execution(identity))
    key = identity.generate_key()

    svc.purge_by_key(PurgeByKeyCommand(key, hard=True))

    assert key in metrics._deleted_keys


def test_hard_delete_one_unknown_key_returns_empty_report():
    svc, _, _, _ = _service()
    report = svc.purge_by_key(PurgeByKeyCommand("nope", hard=True))
    assert report.executions_removed == 0


# --- hard delete: hard_delete_all --------------------------------------------


def test_hard_delete_all_removes_every_key():
    svc, repo, store, _ = _service()
    for i in range(3):
        identity = _identity(str(i))
        content = f"c{i}".encode()
        repo.save(_execution(identity, content=content))
        store.put("blob_" + content.hex(), content)

    report = svc.purge_all(PurgeAllCommand(hard=True))

    assert report.executions_removed == 3
    assert repo.all_execution_keys() == []


def test_hard_delete_all_empty_store_returns_zero_report():
    svc, _, _, _ = _service()
    report = svc.purge_all(PurgeAllCommand(hard=True))
    assert report.executions_removed == 0


# --- shared blob: no orphan deletion when still referenced -------------------


def test_shared_blob_not_deleted_when_still_referenced():
    svc, repo, store, _ = _service()
    id_a = _identity("a")
    id_b = _identity("b")
    shared_content = b"shared"
    shared_blob = "blob_" + shared_content.hex()

    for identity in (id_a, id_b):
        artifact = Artifact(
            artifact_type=ArtifactType.STDOUT,
            blob_key=shared_blob,
            size_bytes=len(shared_content),
            content=shared_content,
        )
        repo.save(
            MlExecution(
                call_identity=identity,
                execution_state=ExecutionState.SUCCESS,
                execution_kind=ExecutionKind.LOCAL_MANAGED,
                output_persisted=True,
                artifacts=[artifact],
            )
        )
    store.put(shared_blob, shared_content)

    svc.purge_by_key(PurgeByKeyCommand(id_a.generate_key()))

    assert store.has(shared_blob)  # id_b still references it


def test_shared_blob_deleted_after_both_purged():
    svc, repo, store, _ = _service()
    id_a = _identity("a")
    id_b = _identity("b")
    shared_content = b"shared"
    shared_blob = "blob_" + shared_content.hex()

    for identity in (id_a, id_b):
        artifact = Artifact(
            artifact_type=ArtifactType.STDOUT,
            blob_key=shared_blob,
            size_bytes=len(shared_content),
            content=shared_content,
        )
        repo.save(
            MlExecution(
                call_identity=identity,
                execution_state=ExecutionState.SUCCESS,
                execution_kind=ExecutionKind.LOCAL_MANAGED,
                output_persisted=True,
                artifacts=[artifact],
            )
        )
    store.put(shared_blob, shared_content)

    svc.purge_by_key(PurgeByKeyCommand(id_a.generate_key()))
    svc.purge_by_key(PurgeByKeyCommand(id_b.generate_key()))

    assert not store.has(shared_blob)


# --- LRU eviction ------------------------------------------------------------


def test_evict_to_quota_no_op_when_under_limit():
    svc, repo, store, _ = _service()
    identity = _identity()
    repo.save(_execution(identity, content=b"small"))
    report = svc.evict_to_quota(EvictToQuotaCommand(max_bytes=1_000_000))
    assert report.executions_removed == 0
    assert report.bytes_freed == 0


def test_evict_to_quota_evicts_least_recently_accessed():
    id_old = _identity("old")
    id_new = _identity("new")
    repo = InMemoryExecutionRepository(FixedClock())
    store = InMemoryBlobStore()

    old_content = b"old_content"  # accessed long ago
    new_content = b"new_content"  # accessed recently
    repo.save(_execution(id_old, content=old_content))
    repo.save(_execution(id_new, content=new_content))
    store.put("blob_" + old_content.hex(), old_content)
    store.put("blob_" + new_content.hex(), new_content)

    # old was accessed at epoch 100, new at epoch 999
    metrics = FakeMetrics(
        last_access={
            id_old.generate_key(): 100.0,
            id_new.generate_key(): 999.0,
        }
    )
    svc = PurgeService(repo, store, metrics, metrics)

    # quota is just under the total — need to evict one execution
    total = len(old_content) + len(new_content)
    report = svc.evict_to_quota(EvictToQuotaCommand(max_bytes=total - 1))

    assert report.executions_removed == 1
    # The old (LRU) execution should be gone; new should remain
    assert repo.find_current(id_old.generate_key()) is None
    assert repo.find_current(id_new.generate_key()) is not None


class _RecordingDiag(DiagnosticsPort):
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def debug(self, msg: str, **context: object) -> None:
        pass

    def info(self, msg: str, **context: object) -> None:
        pass

    def warn(self, msg: str, **context: object) -> None:
        self.warnings.append(msg)

    def error(self, msg: str, exc: BaseException | None = None, **context: object) -> None:
        pass


class _UnreadableAccessMetrics(FakeMetrics):
    """A journal whose access data cannot be read (last_access → None)."""

    def last_access(self) -> dict[str, float] | None:
        return None


def _over_quota_service(metrics, diag):
    repo = InMemoryExecutionRepository(FixedClock())
    store = InMemoryBlobStore()
    repo.save(_execution(_identity("a"), content=b"aaaa"))
    repo.save(_execution(_identity("b"), content=b"bbbb"))
    store.put("blob_" + b"aaaa".hex(), b"aaaa")
    store.put("blob_" + b"bbbb".hex(), b"bbbb")
    return PurgeService(repo, store, metrics, metrics, diag)


def test_evict_to_quota_warns_and_still_enforces_when_access_data_unreadable():
    diag = _RecordingDiag()
    svc = _over_quota_service(_UnreadableAccessMetrics(), diag)
    # total is 8 bytes; a 4-byte quota must still evict one execution even though
    # the LRU access data is unreadable — quota stays enforced on creation time.
    report = svc.evict_to_quota(EvictToQuotaCommand(max_bytes=4))
    assert report.executions_removed == 1
    assert any("degraded" in warning for warning in diag.warnings)


def test_evict_to_quota_does_not_warn_when_registry_is_merely_empty():
    diag = _RecordingDiag()
    svc = _over_quota_service(FakeMetrics(), diag)  # last_access → {} (empty, normal)
    svc.evict_to_quota(EvictToQuotaCommand(max_bytes=4))
    # An empty registry is normal — creation-time ordering, no degraded warning.
    assert diag.warnings == []


def test_evict_to_quota_falls_back_to_creation_time_for_untracked_keys():
    id_a = _identity("a")
    id_b = _identity("b")
    repo = InMemoryExecutionRepository(FixedClock())
    store = InMemoryBlobStore()
    repo.save(_execution(id_a, content=b"content_a"))
    repo.save(_execution(id_b, content=b"content_b"))
    store.put("blob_" + b"content_a".hex(), b"content_a")
    store.put("blob_" + b"content_b".hex(), b"content_b")

    # No access data — creation-time fallback; both entries created_at="" so
    # both get epoch 0.0 and any one of them may be evicted. Validate the
    # service runs without error and evicts exactly enough.
    metrics = FakeMetrics()
    svc = PurgeService(repo, store, metrics, metrics)
    total = len(b"content_a") + len(b"content_b")
    report = svc.evict_to_quota(EvictToQuotaCommand(max_bytes=total - 1))

    assert report.executions_removed >= 1
    assert report.bytes_freed > 0


# --- purge_by_session_tag / hard_delete_by_session_tag -----------------------


def _svc_with_session_tag(tag: str, session_ids: list[str], key_per_session: dict[str, str]):
    """Build a PurgeService wired with executions, one per session under ``tag``."""
    repo, store = _repo_with_entries(list(key_per_session.values()))
    metrics = FakeMetrics(
        session_keys={sid: [key] for sid, key in key_per_session.items()},
    )._with_session_tags({tag: session_ids})
    return PurgeService(repo, store, metrics, metrics), repo


def _repo_with_entries(keys: list[str]):
    repo = InMemoryExecutionRepository(FixedClock())
    blob_store = InMemoryBlobStore()
    for key in keys:
        identity = _identity(prompt=key)
        execution = _execution(identity, content=key.encode())
        repo.save(execution)
        blob_store.put("blob_" + key.encode().hex(), key.encode())
    return repo, blob_store


def test_purge_by_session_tag_removes_executions():
    svc, repo = _svc_with_session_tag(
        "sprint",
        ["s1", "s2"],
        {"s1": "key1", "s2": "key2"},
    )
    report = svc.purge_by_session_tag(PurgeBySessionTagCommand("sprint"))
    assert report.executions_removed == 2


def test_purge_by_session_tag_unknown_tag_is_noop():
    svc, repo = _svc_with_session_tag("sprint", ["s1"], {"s1": "key1"})
    report = svc.purge_by_session_tag(PurgeBySessionTagCommand("ghost"))
    assert report.executions_removed == 0


def test_hard_delete_by_session_tag_removes_executions():
    svc, repo = _svc_with_session_tag(
        "sprint",
        ["s1"],
        {"s1": "key1"},
    )
    report = svc.purge_by_session_tag(PurgeBySessionTagCommand("sprint", hard=True))
    assert report.executions_removed == 1


def test_purge_by_session_tag_deduplicates_shared_keys():
    """A key appearing in two sessions under the same tag is purged only once."""
    repo, blob_store = _repo_with_entries(["shared-key"])
    metrics = FakeMetrics(
        session_keys={"s1": ["shared-key"], "s2": ["shared-key"]},
    )._with_session_tags({"tag": ["s1", "s2"]})
    svc = PurgeService(repo, blob_store, metrics, metrics)
    report = svc.purge_by_session_tag(PurgeBySessionTagCommand("tag"))
    assert report.executions_removed == 1


# ---------------------------------------------------------------------------
# evict_stale (0.15.0)
# ---------------------------------------------------------------------------


def test_evict_stale_removes_entries_older_than_cutoff():
    now = _time_module.time()
    old_epoch = now - 10_000  # clearly older than 1 h
    recent_epoch = now - 60  # clearly within 1 h

    id_old = _identity("old")
    id_recent = _identity("recent")
    old_key = id_old.generate_key()
    recent_key = id_recent.generate_key()

    repo = InMemoryExecutionRepository(FixedClock())
    blob_store = InMemoryBlobStore()
    repo.save(_execution(id_old, b"old"))
    blob_store.put("blob_" + b"old".hex(), b"old")
    repo.save(_execution(id_recent, b"recent"))
    blob_store.put("blob_" + b"recent".hex(), b"recent")

    metrics = FakeMetrics(last_access={old_key: old_epoch, recent_key: recent_epoch})
    svc = PurgeService(repo, blob_store, metrics, metrics)

    report = svc.evict_stale(EvictStaleCommand(max_age_seconds=3600))
    assert report.executions_removed == 1
    assert repo.find_current(old_key) is None or not repo.find_current(old_key).output_persisted
    assert repo.find_current(recent_key) is not None


def test_evict_stale_noop_when_nothing_is_stale():
    now = _time_module.time()
    id1 = _identity("k1")
    id2 = _identity("k2")
    key1, key2 = id1.generate_key(), id2.generate_key()

    repo = InMemoryExecutionRepository(FixedClock())
    blob_store = InMemoryBlobStore()
    repo.save(_execution(id1, b"v1"))
    repo.save(_execution(id2, b"v2"))

    metrics = FakeMetrics(last_access={key1: now - 60, key2: now - 120})
    svc = PurgeService(repo, blob_store, metrics, metrics)

    report = svc.evict_stale(EvictStaleCommand(max_age_seconds=3600))
    assert report.executions_removed == 0


def test_evict_stale_fallback_to_created_at_when_no_access_event():
    repo, blob_store = _repo_with_entries(["never-accessed"])
    # no last_access entry for this key -> falls back to created_at (fixed clock = _MOMENT)
    # _MOMENT is 2026-06-21 09:30 UTC, which is far in the past
    metrics = FakeMetrics(last_access={})
    svc = PurgeService(repo, blob_store, metrics, metrics)

    report = svc.evict_stale(
        EvictStaleCommand(max_age_seconds=60)
    )  # 1 minute — _MOMENT is way older
    assert report.executions_removed == 1


def test_evict_stale_zero_or_negative_max_age_is_noop():
    repo, blob_store = _repo_with_entries(["key1"])
    metrics = FakeMetrics()
    svc = PurgeService(repo, blob_store, metrics, metrics)
    assert svc.evict_stale(EvictStaleCommand(max_age_seconds=0)).executions_removed == 0
    assert svc.evict_stale(EvictStaleCommand(max_age_seconds=-1)).executions_removed == 0


# --- hard_delete_by_tag / hard_delete_by_session ----------------------------


def test_hard_delete_by_tag_removes_tagged_execution():
    svc, repo, store, _ = _service()
    identity = _identity("tagged-key")
    repo.save(_execution(identity, content=b"data"))
    store.put("blob_" + b"data".hex(), b"data")
    key = identity.generate_key()
    repo.add_tags(key, ["my-tag"])

    report = svc.purge_by_tag(PurgeByTagCommand("my-tag", hard=True))

    assert report.executions_removed == 1
    assert repo.find_current(key) is None


def test_hard_delete_by_tag_unknown_tag_returns_empty_report():
    svc, _, _, _ = _service()

    report = svc.purge_by_tag(PurgeByTagCommand("nonexistent-tag", hard=True))

    assert report.executions_removed == 0
    assert report.bytes_freed == 0


def test_hard_delete_by_session_removes_matching_executions():
    identity = _identity("sess-key")
    key = identity.generate_key()
    repo = InMemoryExecutionRepository(FixedClock())
    store = InMemoryBlobStore()
    repo.save(_execution(identity, content=b"answer"))
    store.put("blob_" + b"answer".hex(), b"answer")
    metrics = FakeMetrics(session_keys={"sess-1": [key]})
    svc = PurgeService(repo, store, metrics, metrics)

    report = svc.purge_by_session(PurgeBySessionCommand("sess-1", hard=True))

    assert report.executions_removed == 1
    assert repo.find_current(key) is None


def test_hard_delete_by_session_unknown_session_returns_empty_report():
    svc, _, _, _ = _service()

    report = svc.purge_by_session(PurgeBySessionCommand("no-such-session", hard=True))

    assert report.executions_removed == 0
