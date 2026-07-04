# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RepairStoreService — reconcile artifact persistence against the blob store (C-4)."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.repair.repair_report import RepairReport
from generic_ml_cache_core.application.port.inbound.store_repair.repair_store_use_case import (
    RepairStoreUseCase,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.ml_run_ports import SaveMlRunPort
from generic_ml_cache_core.application.port.outbound.repair_ml_runs_port import RepairMlRunsPort


class RepairStoreService(RepairStoreUseCase):
    """Reconcile each unpersisted run against blob presence — never re-running.

    For every artifact a run failed to finish persisting, check whether its blob is
    actually in the store: present -> mark STORED (the write landed but a crash
    preceded finalize); absent -> mark FAILED (the content is gone). A run whose
    every artifact reconciles to STORED is finalized (servable again); one with any
    missing blob stays non-servable and visibly FAILED, and the user regenerates it
    with a cache-refresh run.
    """

    def __init__(
        self,
        repair_source: RepairMlRunsPort,
        save: SaveMlRunPort,
        blob_store: BlobStorePort,
    ) -> None:
        self._repair_source = repair_source
        self._save = save
        self._blob_store = blob_store

    def repair(self) -> RepairReport:
        runs_recovered = runs_unrecoverable = blobs_reconciled = blobs_missing = 0
        for run in self._repair_source.runs_awaiting_persistence():
            all_present = True
            for blob_key in run.blob_keys:
                if self._blob_store.get(blob_key) is not None:
                    self._save.mark_artifacts_stored(run.execution_id, blob_key)
                    blobs_reconciled += 1
                else:
                    self._save.mark_artifacts_failed(
                        run.execution_id, blob_key, "blob missing on repair"
                    )
                    blobs_missing += 1
                    all_present = False
            if all_present:
                self._save.finalize_output_persisted(run.execution_id)
                runs_recovered += 1
            else:
                runs_unrecoverable += 1
        return RepairReport(
            runs_recovered=runs_recovered,
            runs_unrecoverable=runs_unrecoverable,
            blobs_reconciled=blobs_reconciled,
            blobs_missing=blobs_missing,
        )
