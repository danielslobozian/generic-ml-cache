# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""InProcessExecutionKeyLock: a thread-level per-key lock (no cross-process scope)."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager

from generic_ml_cache_core.application.port.outbound.execution_key_lock_port import (
    ExecutionKeyLockPort,
)

#: A fixed pool of striped locks (W29): bounded memory, no per-key growth. Two keys
#: that hash to the same stripe share a lock — a rare, harmless over-serialization.
#: The locks are RE-ENTRANT (RLock): a thread holding one key's lock may acquire
#: another's even when they collide on a stripe (eviction runs inside a record, X10),
#: which a plain Lock would deadlock on.
_STRIPE_COUNT = 64


class InProcessExecutionKeyLock(ExecutionKeyLockPort):
    """A per-key lock that coordinates only THREADS within one process.

    The thread-level half of the record-once guarantee (the W29 stripe lock), with no
    cross-process scope. It is the right implementation for a single-process embedder
    that never runs a second ``gmlc`` process against the same store, and the test
    double for the use-case suites; the shipped daemon/CLI use the filesystem
    implementation, which composes this behaviour with a per-key OS file lock.
    """

    def __init__(self) -> None:
        self._stripes = tuple(threading.RLock() for _ in range(_STRIPE_COUNT))

    @contextmanager
    def acquire(self, execution_key: str) -> Generator[None]:
        # ``hash`` is per-process (fine — this lock is intra-process only) and ``%``
        # keeps the stripe index in range.
        with self._stripes[hash(execution_key) % _STRIPE_COUNT]:
            yield
