# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemStoreLock: an exclusive store lock for whole-store operations.

Uses SQLite's ``BEGIN EXCLUSIVE`` as the locking mechanism — it acquires an
OS-level file lock that is cross-platform (Linux/macOS/Windows) and is
**released automatically when the process dies**, so a crashed encryption
migration never leaves a stale lock. ``timeout=0`` makes acquisition fail fast
instead of blocking.

SQLite is the *mechanism* here, not the subject of the lock. This lock guards
the store as a whole (e.g. during encrypt/decrypt migrations). Per-job worker
lifecycle locks are a separate concern at the CLI layer.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from generic_ml_cache_core.application.port.out.store_lock_port import StoreLockPort
from generic_ml_cache_core.common.errors import StoreLocked

_FILENAME = "store.lock"


class FilesystemStoreLock(StoreLockPort):
    """Whole-store exclusive lock over ``<store>/store.lock``."""

    def __init__(self, store_root: Path) -> None:
        self._path = Path(store_root) / _FILENAME

    @contextmanager
    def acquire(self) -> Iterator[None]:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=0)
        try:
            connection.execute("BEGIN EXCLUSIVE")
        except sqlite3.OperationalError as exc:
            connection.close()
            raise StoreLocked(
                "the store is locked by another operation "
                "(an encryption migration may be in progress)"
            ) from exc
        try:
            yield
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()
