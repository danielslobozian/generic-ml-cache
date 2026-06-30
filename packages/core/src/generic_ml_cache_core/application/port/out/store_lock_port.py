# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StoreLockPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager


class StoreLockPort(ABC):
    """Outbound port for an exclusive, whole-store lock.

    Used to make the store immutable during an encryption migration. The contract:
    acquisition **fails fast** (raises :class:`StoreLocked`) if another process
    already holds it, and the lock **releases automatically when the holding
    process dies** — so there is never a stale lock to clear by hand.
    """

    @abstractmethod
    def acquire(self) -> AbstractContextManager[None]:
        """Acquire the exclusive lock for the duration of the ``with`` block.
        Raises :class:`StoreLocked` immediately if it is already held."""
