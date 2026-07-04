# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RepairStoreUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.repair.repair_report import RepairReport


class RepairStoreUseCase(ABC):
    """Inbound port for the C-4 reconcile-against-presence repair pass.

    Reconciles runs left non-servable by an interrupted or failed blob write against
    what is actually in the blob store — never re-running the client. A blob that is
    present flips its artifact to STORED (crash recovery); a missing one flips to
    FAILED (its content is gone — the user re-runs with cache refresh)."""

    @abstractmethod
    def repair(self) -> RepairReport:
        """Reconcile every unpersisted run and return what changed."""
