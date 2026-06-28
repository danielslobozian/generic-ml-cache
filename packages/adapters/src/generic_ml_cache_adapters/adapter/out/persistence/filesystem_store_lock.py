# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemStoreLock: an exclusive store lock for whole-store operations.

Uses OS-level file locking (fcntl.flock on Unix/macOS, msvcrt.locking on Windows).
The lock is held by the OS on behalf of the process and is released automatically
when the process exits or crashes — no stale lock files after a crash.
Acquisition fails immediately instead of blocking.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from generic_ml_cache_core.application.port.out.store_lock_port import StoreLockPort
from generic_ml_cache_core.common.errors import StoreLocked

_FILENAME = "store.lock"


def _lock_exclusive(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


class FilesystemStoreLock(StoreLockPort):
    """Whole-store exclusive lock over ``<store>/store.lock``."""

    def __init__(self, store_root: Path) -> None:
        self._path = Path(store_root) / _FILENAME

    @contextmanager
    def acquire(self) -> Iterator[None]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self._path), os.O_CREAT | os.O_WRONLY)
        except OSError as exc:
            raise StoreLocked(
                "the store is locked by another operation "
                "(an encryption migration may be in progress)"
            ) from exc
        try:
            _lock_exclusive(fd)
        except OSError as exc:
            os.close(fd)
            raise StoreLocked(
                "the store is locked by another operation "
                "(an encryption migration may be in progress)"
            ) from exc
        try:
            yield
        finally:
            _unlock(fd)
            os.close(fd)
