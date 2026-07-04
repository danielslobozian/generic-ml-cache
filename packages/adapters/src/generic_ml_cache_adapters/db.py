# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Minimal structural (DBAPI2-shaped) protocol for a database connection.

This is the injection SEAM, not a portability layer: core forbids importing a
database driver, so adapters and tests depend on this structural protocol and the
caller injects a concrete connection factory. The protocol is generic, but the SQL
the shipped adapters write against it is SQLite-dialect (``PRAGMA``, ``INSERT OR
IGNORE``, ``lastrowid``, ``?`` placeholders) — so a different engine needs its own
adapter, not merely a different connection. Portability = implement the port.
"""

from __future__ import annotations

from typing import Any, Protocol


class DbCursor(Protocol):
    lastrowid: int | None
    rowcount: int

    def fetchone(self) -> Any: ...

    def fetchall(self) -> list[Any]: ...


class DbConnection(Protocol):
    def execute(self, sql: str, parameters: Any = ...) -> DbCursor: ...

    def executescript(self, sql_script: str) -> DbCursor:
        """Execute a multi-statement SQL script in one native call.

        The driver parses the statement boundaries itself — correctly, even when a
        ``;`` appears inside a trigger body or a string literal — so callers never
        hand-split on ``;``. The migration runner relies on this. (DBAPI2 does not
        mandate this method, but every engine the shipped adapters target provides
        it; a driver that lacks it needs its own migration adapter.)"""
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...
