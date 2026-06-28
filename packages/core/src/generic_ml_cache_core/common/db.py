# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Minimal structural type for a PEP 249 (DBAPI2) database connection.

Core uses this Protocol instead of importing a concrete driver (e.g.
``sqlite3.Connection``) so the SQL layer stays driver-agnostic: any PEP 249
compliant connection — SQLite, PostgreSQL, MariaDB — satisfies the contract.
"""

from __future__ import annotations

from typing import Any, List, Protocol


class DbCursor(Protocol):
    lastrowid: int | None
    rowcount: int

    def fetchone(self) -> Any: ...

    def fetchall(self) -> List[Any]: ...


class DbConnection(Protocol):
    def execute(self, sql: str, parameters: Any = ...) -> DbCursor: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...
