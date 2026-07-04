# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemStoreLock: a whole-store readers-writer lock.

Uses OS-level file locking (fcntl.flock on Unix/macOS, msvcrt.locking on Windows).
The lock is held by the OS on behalf of the process and is released automatically
when the process exits or crashes — no stale lock files after a crash.

Three modes: the fail-fast exclusive acquire (X8, the encryption migration) raises
``StoreLocked`` at once when a peer holds the store; the shared acquire (the normal
content write) blocks while an exclusive holder runs, then proceeds; the
blocking-exclusive acquire (Y1, the first-init migration) WAITS for any holder to
release, then proceeds — so a second process racing a fresh store waits its turn and
no-ops rather than colliding. Shared locking is an fcntl (Unix/macOS) capability;
msvcrt has no shared mode, so on Windows the shared acquire is a documented no-op — the
migration's exclusive lock is not enforced against a concurrent writer there (a
best-effort gap on the secondary platform for this single-user local tool). On Windows
the blocking-exclusive acquire uses ``msvcrt.locking(LK_LOCK)``, which retries for ~10s
before raising rather than blocking indefinitely (the platform's closest analogue).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from generic_ml_cache_core.application.port.outbound.store_lock_port import StoreLockPort
from generic_ml_cache_core.common.errors import StoreLocked

_FILENAME = "store.lock"


def _lock_exclusive(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _lock_exclusive_blocking(fd: int) -> None:
    """Take an exclusive lock, WAITING for any holder to release (Y1). Unlike
    :func:`_lock_exclusive`'s ``LOCK_NB``, this blocks. On Windows ``LK_LOCK`` retries
    for ~10s before raising (msvcrt has no unbounded blocking mode)."""
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)


def _unlock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


def _lock_shared_blocking(fd: int) -> bool:
    """Take a shared (read) lock, BLOCKING until any exclusive holder releases.
    Returns whether a real lock was taken — False on Windows, which has no advisory
    shared mode via msvcrt (the shared acquire is then a no-op there)."""
    if sys.platform == "win32":
        return False
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_SH)
    return True


class FilesystemStoreLock(StoreLockPort):
    """Whole-store readers-writer lock over ``<store>/store.lock``."""

    def __init__(self, store_root: Path) -> None:
        self._path = Path(store_root) / _FILENAME

    @contextmanager
    def acquire(self) -> Generator[None]:
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

    @contextmanager
    def acquire_exclusive_blocking(self) -> Generator[None]:
        # The first-init migration path (Y1): a second process racing a fresh store
        # WAITS for the first to finish migrating, then reads version==current and
        # no-ops. Unlike acquire() (X8, fail-fast for the encryption migration) this
        # BLOCKS rather than raising StoreLocked — the point is to serialize concurrent
        # first-touches so they can't double-seed schema_version or collide on the DDL.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._path), os.O_CREAT | os.O_WRONLY)
        try:
            _lock_exclusive_blocking(fd)
        except OSError as exc:
            os.close(fd)
            raise StoreLocked(
                "the store is locked by another operation (a migration may be in progress)"
            ) from exc
        try:
            yield
        finally:
            _unlock(fd)
            os.close(fd)

    @contextmanager
    def acquire_shared(self) -> Generator[None]:
        # The normal content-write path: coexist with other writers, wait out a
        # migration. Unlike the exclusive acquire this BLOCKS (a write should wait the
        # rare migration out, not fail), so no StoreLocked is raised here.
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self._path), os.O_CREAT | os.O_RDONLY)
        locked = _lock_shared_blocking(fd)
        try:
            yield
        finally:
            if locked:
                _unlock(fd)
            os.close(fd)
