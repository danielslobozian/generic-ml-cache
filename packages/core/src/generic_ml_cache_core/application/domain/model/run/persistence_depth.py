# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PersistenceDepth."""

from __future__ import annotations

from enum import Enum


class PersistenceDepth(Enum):
    """How much of an execution is kept on disk — a single ordered choice.

    Each level is a superset of the one below, so the degenerate "input stored
    without output" state is unrepresentable:

    - ``METER``   -- metadata/usage only. The call runs and is recorded, but no
      output is stored, so it is never replayed (a usage/observability mode).
    - ``CACHE``   -- ``METER`` plus the output: stored and replayed on a hit. The
      default, and today's behaviour.
    - ``DATASET`` -- ``CACHE`` plus the input: replayed and retained as a labelled
      ``(input, output)`` pair.
    """

    METER = "meter"
    CACHE = "cache"
    DATASET = "dataset"

    @property
    def stores_output(self) -> bool:
        """Whether this depth keeps the output (``CACHE`` and ``DATASET``)."""
        return self in (PersistenceDepth.CACHE, PersistenceDepth.DATASET)

    @property
    def stores_input(self) -> bool:
        """Whether this depth keeps the input (``DATASET`` only)."""
        return self is PersistenceDepth.DATASET
