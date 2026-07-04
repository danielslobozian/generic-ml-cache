# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RepairMlRunsPort — the read side of the C-4 reconcile-against-presence pass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.execution.execution_id import ExecutionId


@dataclass(frozen=True)
class UnpersistedRun:
    """A run whose latest execution never finished persisting: it is not servable
    (``output_persisted`` is false) and carries the ``execution_id`` and the
    ``blob_keys`` of its artifacts that are not yet STORED. Repair checks each blob's
    presence and marks it STORED or FAILED by ``execution_id`` accordingly."""

    execution_key: str
    execution_id: ExecutionId
    blob_keys: tuple[str, ...]


class RepairMlRunsPort(ABC):
    """Find the runs a repair pass must reconcile."""

    @abstractmethod
    def runs_awaiting_persistence(self) -> list[UnpersistedRun]:
        """Return one entry per key whose LATEST execution is not output-persisted
        and still has non-STORED artifacts — the reconcile worklist. Marking targets
        the latest execution, so only latest-incomplete runs are returned (a key with
        a newer servable run is already complete and is skipped)."""
