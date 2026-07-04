# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SQLite connection-factory construction.

Core accepts a ``Callable[[], Connection]`` for all database access and forbids
importing a driver itself. This module provides the shipped SQLite factory builder,
used by the CLI and daemon to construct and inject the factory without pulling
``sqlite3`` into core. It is SQLite-specific (it imports ``sqlite3`` and sets the
``foreign_keys`` PRAGMA); another engine ships its own factory + adapter.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from sqlite3 import Connection

#: How long a connection waits for a lock before raising ``database is locked``.
#: Two processes on one store (a CLI run while the daemon writes) then WAIT their
#: turn instead of erroring — the S2a "transient contention → retry" behaviour,
#: handled by SQLite itself. The in-process ``threading.Lock`` in the cached
#: service only stops same-process duplicate work; cross-process correctness is
#: the database's job (Decision W1).
_BUSY_TIMEOUT_MS = 5000


def sqlite_connection_factory(
    db_path: Path,
    *,
    check_same_thread: bool = True,
) -> Callable[[], Connection]:
    """Return a factory that opens a fresh SQLite connection to *db_path* on each call.

    The caller owns the connection lifecycle and must close each connection after use.

    Args:
        db_path: Absolute path to the SQLite database file.
        check_same_thread: Pass ``False`` when the factory is shared across threads
            (e.g. the daemon's async thread pool). Defaults to ``True`` for
            single-threaded callers such as the CLI.
    """
    resolved = Path(db_path)

    def _connect() -> Connection:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(resolved), check_same_thread=check_same_thread)
        # SQLite enforces foreign keys only when asked, per connection (OFF by default).
        # Without this every FK/ON DELETE CASCADE in the schema is silently inert.
        connection.execute("PRAGMA foreign_keys = ON")
        # WAL lets a reader and a writer proceed concurrently (a CLI read need not
        # block behind the daemon's write); busy_timeout makes a would-be
        # "database is locked" WAIT for the lock rather than fail immediately.
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_MS}")
        return connection

    return _connect
