# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The shipped SQLite persistence adapter.

The library ships ONE batteries-included persistence adapter — SQLite — behind the
core outbound ports. It is not a portability layer: the SQL is SQLite-dialect
(``PRAGMA``, ``INTEGER PRIMARY KEY``, ``INSERT OR IGNORE``, ``lastrowid``, ``?``
placeholders). An embedder wanting Postgres/S3 implements the ports and injects
their own adapter (portability = port + inject, never a shared dialect layer)."""
