# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""A conformance TCK for the ML-run persistence ports (E-1, V6).

A reusable behavioral contract every persistence backend must satisfy — the shipped
SQLite adapter and the in-memory reference fake both pass it, so the fake cannot
drift from the real store (Fowler's Contract Test), and a third-party backend author
proves their adapter by subclassing it. Subclass ``MlRunStoreConformance`` in a test
module and implement ``make_store`` to return a fresh, empty store bound to the given
``tmp_path``; pytest then collects the inherited ``test_*`` methods.

Needs pytest (this module is behind the core ``[test]`` extra), but is itself pure
domain — it never imports an adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pytest

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
from generic_ml_cache_core.application.domain.model.execution.execution_id import ExecutionId
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.port.outbound.ml_run_ports import ExecutionSizeEntry
from generic_ml_cache_core.application.port.outbound.repair_ml_runs_port import UnpersistedRun
from generic_ml_cache_core.common.errors import StoreConsistencyError


class MlRunStore(Protocol):
    """The slice of the persistence ports the conformance TCK exercises — a
    structural type, so any backend (the fake, the SQLite adapter) satisfies it
    without inheriting a header interface."""

    def find_current(self, execution_key: str) -> MlExecution | None: ...
    def find_all(self, execution_key: str) -> list[MlExecution]: ...
    def save(self, execution: MlExecution) -> None: ...
    def record_outcome(self, execution: MlExecution) -> None: ...
    def persist_artifact(self, execution_id: ExecutionId, artifact: Artifact) -> None: ...
    def mark_artifacts_stored(self, execution_id: ExecutionId, blob_key: BlobKey) -> None: ...
    def mark_artifacts_failed(
        self, execution_id: ExecutionId, blob_key: BlobKey, detail: str
    ) -> None: ...
    def finalize_output_persisted(self, execution_id: ExecutionId) -> None: ...
    def remove_execution(self, execution_id: ExecutionId) -> None: ...
    def runs_awaiting_persistence(self) -> list[UnpersistedRun]: ...
    def soft_purge_execution(self, execution_key: str) -> None: ...
    # Accounting / retention surface (X24): quota, size summaries, blob-key collection,
    # tagging, and hard delete — where a third-party backend most easily diverges.
    def add_tags(self, execution_key: str, tags: list[str]) -> None: ...
    def tags_for(self, execution_key: str) -> list[str]: ...
    def total_stored_bytes(self) -> int: ...
    def blob_keys_for_execution(self, execution_key: str) -> list[BlobKey]: ...
    def hard_delete_execution(self, execution_key: str) -> None: ...
    def current_executions_with_sizes(self) -> list[ExecutionSizeEntry]: ...
    def executions_by_tag(self, tag: str) -> list[str]: ...


def _identity(prompt: str = "p") -> ManagedCallIdentity:
    return ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="c",
        prompt_fingerprint=prompt,
    )


def _artifact(
    content: bytes = b"answer", *, status: ArtifactStatus = ArtifactStatus.STORED
) -> Artifact:
    return Artifact(
        artifact_type=ArtifactType.STDOUT,
        blob_key=BlobKey("blob" + content.hex()),
        size_bytes=len(content),
        content=content,
        status=status,
    )


def _servable(identity: ManagedCallIdentity, content: bytes = b"answer") -> MlExecution:
    return MlExecution(
        call_identity=identity,
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=True,
        artifacts=[_artifact(content)],
    )


def _pending(identity: ManagedCallIdentity, content: bytes = b"answer") -> MlExecution:
    """A run as the C-4 DB-first path saves it: not yet servable, artifact PENDING."""
    return MlExecution(
        call_identity=identity,
        execution_state=ExecutionState.SUCCESS,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
        artifacts=[_artifact(content, status=ArtifactStatus.PENDING)],
    )


def _in_progress(
    identity: ManagedCallIdentity,
    *,
    execution_id: ExecutionId | None = None,
    state: ExecutionState = ExecutionState.IN_PROGRESS,
) -> MlExecution:
    """An IN_PROGRESS row (no artifacts) as the W1 write path first saves it. Pass
    ``execution_id`` to build the transition payload for ``record_outcome`` (same
    id, final state)."""
    execution = MlExecution(
        call_identity=identity,
        execution_state=state,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
        artifacts=[],
    )
    if execution_id is not None:
        execution.execution_id = execution_id
    return execution


class MlRunStoreConformance:
    """The behavioral contract for an ml-run persistence store. Subclass + implement
    ``make_store``; the shipped SQLite adapter and the reference fake both pass this."""

    def make_store(self, tmp_path: Path) -> MlRunStore:
        raise NotImplementedError

    def test_find_current_is_none_for_unknown_key(self, tmp_path: Path) -> None:
        assert self.make_store(tmp_path).find_current("nope") is None

    def test_save_servable_then_find_current(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        store.save(_servable(identity))
        found = store.find_current(identity.generate_key())
        assert found is not None
        assert found.execution_state is ExecutionState.SUCCESS

    def test_a_new_servable_success_supersedes_the_prior_one(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity, b"old"))
        store.save(_servable(identity, b"new"))
        assert len(store.find_all(key)) == 2  # append-only history
        current = store.find_current(key)
        assert current is not None
        assert current.artifacts[0].blob_key == BlobKey("blob" + b"new".hex())

    def test_db_first_lifecycle_pending_then_stored_then_finalized(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        blob_key = _artifact().blob_key
        execution = _pending(identity)
        store.save(execution)
        assert store.find_current(key) is None  # PENDING -> not servable
        store.mark_artifacts_stored(execution.execution_id, blob_key)
        assert store.find_current(key) is None  # stored but not finalized
        store.finalize_output_persisted(execution.execution_id)
        current = store.find_current(key)
        assert current is not None and current.output_persisted is True

    def test_failed_artifact_blocks_servability(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        blob_key = _artifact().blob_key
        execution = _pending(identity)
        store.save(execution)
        store.mark_artifacts_failed(execution.execution_id, blob_key, "disk full")
        assert store.find_current(key) is None  # a FAILED artifact is never servable

    def test_per_document_path_via_persist_artifact(self, tmp_path: Path) -> None:
        # The service's W1 path: save an IN_PROGRESS row (no artifacts), transition
        # it, then append + resolve each document one at a time by execution_id.
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        in_progress = _in_progress(identity)
        store.save(in_progress)
        store.record_outcome(
            _in_progress(
                identity, execution_id=in_progress.execution_id, state=ExecutionState.SUCCESS
            )
        )
        artifact = _artifact(status=ArtifactStatus.PENDING)
        store.persist_artifact(in_progress.execution_id, artifact)
        store.mark_artifacts_stored(in_progress.execution_id, artifact.blob_key)
        store.finalize_output_persisted(in_progress.execution_id)
        assert store.find_current(key) is not None

    def test_finalize_targets_its_own_row_not_the_latest_by_key(self, tmp_path: Path) -> None:
        # The W1 corruption fix: with two rows for one key, finalizing the OLDER row
        # must promote THAT row, not the latest one a concurrent writer inserted.
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        older = _pending(identity, content=b"old")
        newer = _pending(identity, content=b"new")
        store.save(older)
        store.save(newer)  # newer is the latest row by key
        store.mark_artifacts_stored(older.execution_id, BlobKey("blob" + b"old".hex()))
        store.finalize_output_persisted(older.execution_id)  # target the OLDER row
        current = store.find_current(key)
        assert current is not None
        assert current.artifacts[0].blob_key == BlobKey("blob" + b"old".hex())

    def test_finalize_requires_every_artifact_stored(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        execution = _pending(identity)  # its artifact is PENDING, never marked STORED
        store.save(execution)
        with pytest.raises(StoreConsistencyError):
            store.finalize_output_persisted(execution.execution_id)

    def test_mark_on_unknown_execution_id_raises(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        with pytest.raises(StoreConsistencyError):
            store.mark_artifacts_stored(ExecutionId.generate(), _artifact().blob_key)

    def test_finalize_on_unknown_execution_id_raises(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        with pytest.raises(StoreConsistencyError):
            store.finalize_output_persisted(ExecutionId.generate())

    def test_remove_execution_deletes_only_that_row(self, tmp_path: Path) -> None:
        # Removing the IN_PROGRESS row of an interrupted run must not touch a prior
        # servable run for the same key (S3c-ii).
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity, b"kept"))
        interrupted = _in_progress(identity)
        store.save(interrupted)
        assert len(store.find_all(key)) == 2
        store.remove_execution(interrupted.execution_id)
        remaining = store.find_all(key)
        assert len(remaining) == 1
        assert remaining[0].artifacts[0].blob_key == BlobKey("blob" + b"kept".hex())

    def test_remove_execution_is_idempotent(self, tmp_path: Path) -> None:
        self.make_store(tmp_path).remove_execution(ExecutionId.generate())  # must not raise

    def test_runs_awaiting_persistence_lists_the_unfinished_run(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_pending(identity))
        awaiting = store.runs_awaiting_persistence()
        assert [run.execution_key for run in awaiting] == [key]

    def test_soft_purge_releases_artifacts_and_unservables(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity))
        store.soft_purge_execution(key)
        assert store.find_current(key) is None

    # -- accounting / retention (X24) -----------------------------------------

    def test_total_stored_bytes_sums_the_current_stored_artifacts(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        store.save(_servable(_identity("a"), b"aaaa"))  # 4 bytes
        store.save(_servable(_identity("b"), b"bbbbbb"))  # 6 bytes
        assert store.total_stored_bytes() == 10

    def test_total_stored_bytes_excludes_a_non_servable_run(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        store.save(_servable(_identity("a"), b"aaaa"))
        store.save(_pending(_identity("b"), b"bbbbbb"))  # not output_persisted → uncounted
        assert store.total_stored_bytes() == 4

    def test_blob_keys_for_execution_lists_the_owned_keys(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        store.save(_servable(identity, b"answer"))
        keys = store.blob_keys_for_execution(identity.generate_key())
        assert keys == [BlobKey("blob" + b"answer".hex())]

    def test_current_executions_with_sizes_reports_the_servable_sizes(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        store.save(_servable(identity, b"answer"))
        entries = store.current_executions_with_sizes()
        assert [(e.execution_key, e.total_size_bytes) for e in entries] == [
            (identity.generate_key(), len(b"answer"))
        ]

    def test_hard_delete_execution_removes_all_history(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity, b"old"))
        store.save(_servable(identity, b"new"))  # append-only history: two rows
        store.hard_delete_execution(key)
        assert store.find_all(key) == []

    def test_executions_by_tag_returns_the_tagged_current_key(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity))
        store.add_tags(key, ["keep"])
        assert store.executions_by_tag("keep") == [key]
        assert store.executions_by_tag("absent") == []

    def test_tags_for_returns_the_current_rows_tags(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity))
        store.add_tags(key, ["keep", "review"])
        assert store.tags_for(key) == ["keep", "review"]  # sorted, on the current row

    def test_tags_do_not_carry_across_supersession(self, tmp_path: Path) -> None:
        # Y16: tags belong to an execution ROW (its execution_id), not the key. After a
        # new servable success supersedes the tagged one, the new current row is
        # untagged — this is exactly the seam where a key-scoped fake would diverge.
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity, b"old"))
        store.add_tags(key, ["keep"])
        store.save(_servable(identity, b"new"))  # supersedes the tagged row
        assert store.tags_for(key) == []
        assert store.executions_by_tag("keep") == []

    def test_tags_are_hidden_once_a_soft_purge_unservables_the_row(self, tmp_path: Path) -> None:
        # soft_purge clears artifacts + output_persisted, so the row is no longer
        # current; tags_for / executions_by_tag key off the current row, so both empty.
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity))
        store.add_tags(key, ["keep"])
        store.soft_purge_execution(key)
        assert store.tags_for(key) == []
        assert store.executions_by_tag("keep") == []

    def test_tags_are_deleted_by_a_hard_delete(self, tmp_path: Path) -> None:
        store = self.make_store(tmp_path)
        identity = _identity()
        key = identity.generate_key()
        store.save(_servable(identity))
        store.add_tags(key, ["keep"])
        store.hard_delete_execution(key)
        assert store.tags_for(key) == []
        assert store.executions_by_tag("keep") == []
