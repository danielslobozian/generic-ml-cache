# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionId — a domain-minted surrogate identity for one execution (W1, V6)."""

from __future__ import annotations

import uuid


class ExecutionId(str):
    """A per-execution surrogate identity, minted by the domain the instant an
    execution is created — before it ever touches the store.

    It is the STABLE handle the DB-first write path targets: mark/finalize update
    the one row ``WHERE execution_id = ?``, never "the latest row by key", so a
    concurrent second writer's newer row can never be mistargeted (W1). The domain
    owns identity at construction (the DDD ``@PrePersist``-UUID default), not the
    database (``@GeneratedValue`` would need a save→lastrowid round-trip and couple
    the store to integer autoincrement).

    A UUID4 string: collision-free without a round-trip and engine-independent. A
    ``str`` subclass so it drops in as a SQL parameter and dict key, exactly like
    :class:`BlobKey`.
    """

    __slots__ = ()

    @classmethod
    def generate(cls) -> ExecutionId:
        """Mint a fresh, unique execution identity."""
        return cls(str(uuid.uuid4()))
