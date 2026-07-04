# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PurgeReport."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PurgeReport:
    """The outcome of a purge or eviction operation.

    ``executions_removed`` is the number of execution keys processed.
    ``bytes_freed`` is the total size of the blobs removed, summed directly from
    what was deleted (each blob is owned by one execution, so every removed blob's
    bytes are freed exactly once). ``blobs_removed`` is the number of blob files
    actually deleted from the blob store.
    """

    executions_removed: int
    bytes_freed: int
    blobs_removed: int
