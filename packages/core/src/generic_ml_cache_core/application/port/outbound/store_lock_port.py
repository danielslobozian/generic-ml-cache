# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StoreLockPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager


class StoreLockPort(ABC):
    """Outbound port for a whole-store readers-writer lock.

    A single-writer / many-reader lock over the store: the (rare, short) encryption
    migration takes it **exclusive** to make the store immutable while it transforms
    the blobs; the normal content-write path takes it **shared**, so concurrent writes
    still run together but are all excluded during a migration (X8). The lock
    **releases automatically when the holding process dies** — no stale lock to clear
    by hand. Fixes the pre-X8 one-sided lock, where only the migration acquired it and
    a concurrent write could drop a plaintext blob into a store being encrypted.
    """

    @abstractmethod
    def acquire(self) -> AbstractContextManager[None]:
        """Acquire the EXCLUSIVE lock for the duration of the ``with`` block — used by
        the encryption migration. Raises :class:`StoreLocked` immediately (fail-fast)
        if any other holder (exclusive or shared) already holds it."""

    @abstractmethod
    def acquire_shared(self) -> AbstractContextManager[None]:
        """Acquire a SHARED (read) lock for the duration of the ``with`` block — used
        by the normal content-write path. Many shared holders coexist; it BLOCKS while
        an exclusive migration holds the lock, then proceeds once it releases (a write
        waits the migration out rather than corrupting a half-encrypted store)."""
