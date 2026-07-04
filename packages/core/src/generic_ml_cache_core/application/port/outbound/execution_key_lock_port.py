# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionKeyLockPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager


class ExecutionKeyLockPort(ABC):
    """Outbound port for a blocking, per-execution-key mutual-exclusion lock (X7).

    Held around the re-check-then-run critical section of a cache miss so that only
    one caller runs the expensive client call for a given key while the others wait
    and then serve the freshly-recorded hit — the "record once" guarantee. Unlike
    :class:`StoreLockPort` (a whole-store lock that fails fast), this is:

    - **per key**: two different keys never block each other;
    - **blocking**: a contender WAITS for the holder rather than failing;
    - **bounded**: the wait has a ceiling, after which the caller PROCEEDS to run
      anyway (degrading to the possible-duplicate-*work* of the pre-X7 world) rather
      than failing the user's call because a peer hung — a hung peer must never block
      the user entirely.

    The default filesystem implementation spans BOTH levels behind one ``acquire``:
    a per-key in-process lock (thread-level, the W29 stripe) AND a per-key OS file
    lock (process-level), so the guarantee holds across daemon threads, CLI-vs-CLI,
    CLI-vs-daemon, and embedded-vs-CLI. An embedder on non-filesystem infrastructure
    (Postgres/S3) implements this port their way (e.g. a Postgres advisory lock).
    """

    @abstractmethod
    def acquire(self, execution_key: str) -> AbstractContextManager[None]:
        """Acquire the lock for ``execution_key`` for the duration of the ``with``
        block, blocking until it is free or the bounded timeout elapses (after which
        it proceeds without the cross-process lock). Never raises to fail the call."""
