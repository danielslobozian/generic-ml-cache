# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Connection factory construction for PEP 249 datasources.

Core accepts a ``Callable[[], Connection]`` for all database access. This module
provides the canonical factory builder for SQLite, used by the CLI and daemon to
construct and inject the factory without importing ``sqlite3`` into core.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from sqlite3 import Connection


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
        return connection

    return _connect
