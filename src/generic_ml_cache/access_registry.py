# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The access registry: a side log of cache access events for observability.

It is **non-load-bearing by construction** -- it records *that* a hit / miss /
record / eviction happened, for `stats` and `prune` to read, but it never gates
correctness. Every operation swallows its own errors: if the database is missing,
locked, unwritable, or corrupt, the cache still resolves exactly as it would
without it. It is deliberately separate from the cassettes, which stay pure and
immutable -- no access counters are ever written back into a recording.

Stored in the store directory as ``registry.sqlite3`` (stdlib ``sqlite3`` only;
no third-party dependency). It carries no integrity/checksum role: a checksum kept
beside the data it guards, in a folder the user can write, protects nothing a
determined editor couldn't also rewrite -- so we don't pretend to.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# The four access events. A resolve emits exactly one of HIT / MISS / RECORD
# (passthrough calls are outside cache accounting and emit nothing); EVICT is
# emitted by prune/eviction when a cassette is removed.
HIT = "hit"
MISS = "miss"
RECORD = "record"
EVICT = "evict"

_DB_NAME = "registry.sqlite3"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    event     TEXT NOT NULL,
    match_key TEXT,
    client    TEXT,
    model     TEXT,
    effort    TEXT
)
"""


class AccessRegistry:
    """A best-effort SQLite log of access events, living beside the cassettes."""

    def __init__(self, root: Path) -> None:
        self._path = Path(root) / _DB_NAME

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path)
        conn.execute(_SCHEMA)
        return conn

    def record(
        self,
        event: str,
        *,
        match_key: Optional[str],
        client: str,
        model: str,
        effort: str,
    ) -> None:
        """Append one access event. Never raises -- failures are swallowed so the
        cache is never affected by the registry being unavailable."""
        try:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO access_events (ts, event, match_key, client, model, effort) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        event,
                        match_key,
                        client,
                        model,
                        effort,
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            # Non-load-bearing: observability must never break the cache.
            pass

    def event_counts(self) -> Dict[str, int]:
        """Return {event: count} across all recorded events ({} if unavailable)."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT event, COUNT(*) FROM access_events GROUP BY event"
                ).fetchall()
                return {event: count for event, count in rows}
            finally:
                conn.close()
        except Exception:
            return {}
