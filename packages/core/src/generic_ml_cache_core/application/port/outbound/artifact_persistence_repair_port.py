# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ArtifactPersistenceRepairPort — resolve an execution's artifact persistence (X21)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
from generic_ml_cache_core.application.domain.model.execution.execution_id import ExecutionId


class ArtifactPersistenceRepairPort(ABC):
    """Resolve the persistence status of an execution's artifacts and finalize it.

    The narrow role ``RepairStoreService`` needs (X21, ISP): mark each artifact
    STORED/FAILED against blob presence and finalize the run once every artifact is
    STORED — nothing of the wider write path (``save``/``record_outcome``/
    ``persist_artifact``/``remove_execution``). The full write port
    :class:`SaveMlRunPort` extends this, so the one repository impl satisfies both and a
    repair-only backend need not implement the whole write path it never calls.
    """

    @abstractmethod
    def mark_artifacts_stored(self, execution_id: ExecutionId, blob_key: BlobKey) -> None:
        """Flip every artifact of the execution identified by ``execution_id`` that
        references ``blob_key`` to ``STORED`` and stamp ``persisted_at`` — the blob
        is confirmed in the store. Two artifacts sharing a blob (e.g. empty
        stdout+stderr) are marked together; one blob backs both. Raises
        ``StoreConsistencyError`` if no such artifact row exists to update."""

    @abstractmethod
    def mark_artifacts_failed(
        self, execution_id: ExecutionId, blob_key: BlobKey, detail: str
    ) -> None:
        """Flip every artifact of the execution identified by ``execution_id`` that
        references ``blob_key`` to ``FAILED`` with ``detail`` — the blob write did
        not land, so the run cannot become servable and the failure is visible in
        read views. Raises ``StoreConsistencyError`` if there is no row to update."""

    @abstractmethod
    def finalize_output_persisted(self, execution_id: ExecutionId) -> None:
        """Mark the execution identified by ``execution_id`` output-persisted
        (servable) and supersede the prior current execution — called once all its
        artifacts are ``STORED``. The deferred half of ``save``'s supersession under
        DB-first ordering. Raises ``StoreConsistencyError`` if the id is unknown or
        any of its artifacts is not yet STORED (finalize must never make a run with a
        missing blob servable)."""
