# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RepairStoreService (C-4 reconcile-against-presence)."""

from __future__ import annotations

from datetime import datetime, timezone

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.clock_port import ClockPort
from generic_ml_cache_core.application.usecase.repair_store_service import RepairStoreService
from generic_ml_cache_core.testing.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)

_MOMENT = datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return _MOMENT


class InMemoryBlobStore(BlobStorePort):
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    def put(self, key: str, output: bytes) -> None:
        self.store[key] = output

    def is_healthy(self) -> bool:
        return True

    def remove(self, key: str) -> None:
        self.store.pop(key, None)


def _identity(prompt: str = "p") -> ManagedCallIdentity:
    return ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="c",
        prompt_fingerprint=prompt,
    )


def _save_pending(repo, identity, blob_key: str) -> str:
    """Save a run as the DB-first path leaves it mid-flight: PENDING, not servable."""
    key = identity.generate_key()
    repo.save(
        MlExecution(
            call_identity=identity,
            execution_state=ExecutionState.SUCCESS,
            execution_kind=ExecutionKind.LOCAL_MANAGED,
            output_persisted=False,
            artifacts=[
                Artifact(
                    artifact_type=ArtifactType.STDOUT,
                    blob_key=blob_key,
                    size_bytes=3,
                    content=None,
                    status=ArtifactStatus.PENDING,
                )
            ],
        )
    )
    return key


def _service(repo, blob):
    return RepairStoreService(repair_source=repo, save=repo, blob_store=blob)


def test_repair_recovers_a_run_whose_blob_is_present():
    repo = InMemoryExecutionRepository(clock=FixedClock())
    blob = InMemoryBlobStore()
    key = _save_pending(repo, _identity(), "blob-a")
    blob.put("blob-a", b"hi")  # the blob landed; a crash preceded finalize

    report = _service(repo, blob).repair()

    assert report.runs_recovered == 1
    assert report.blobs_reconciled == 1
    assert report.runs_unrecoverable == 0
    current = repo.find_current(key)
    assert current is not None and current.output_persisted is True
    assert current.artifacts[0].status is ArtifactStatus.STORED


def test_repair_marks_a_run_failed_when_its_blob_is_missing():
    repo = InMemoryExecutionRepository(clock=FixedClock())
    blob = InMemoryBlobStore()
    key = _save_pending(repo, _identity(), "blob-gone")  # no blob ever stored

    report = _service(repo, blob).repair()

    assert report.runs_unrecoverable == 1
    assert report.blobs_missing == 1
    assert report.runs_recovered == 0
    assert repo.find_current(key) is None
    assert repo.find_all(key)[-1].artifacts[0].status is ArtifactStatus.FAILED


def test_repair_is_a_no_op_when_nothing_is_pending():
    repo = InMemoryExecutionRepository(clock=FixedClock())
    report = _service(repo, InMemoryBlobStore()).repair()
    assert report == report.__class__(0, 0, 0, 0)
