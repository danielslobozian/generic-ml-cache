# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RepairReport — the outcome of a reconcile-against-presence repair pass (C-4)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairReport:
    """What a repair pass did.

    ``runs_recovered`` are runs whose every non-STORED artifact turned out to have
    a blob present (a crash after the blob landed but before finalize) — they were
    reconciled to STORED and finalized, so they are servable again.
    ``runs_unrecoverable`` are runs with at least one truly-missing blob: those
    artifacts were marked FAILED and the run stays non-servable (the content is
    gone; the user re-runs with cache refresh to regenerate it).
    ``blobs_reconciled`` / ``blobs_missing`` count the artifacts flipped to STORED
    vs FAILED across the whole pass.
    """

    runs_recovered: int
    runs_unrecoverable: int
    blobs_reconciled: int
    blobs_missing: int
