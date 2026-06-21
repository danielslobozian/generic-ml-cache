# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The access registry: a side log of cache access events for observability.

It is **non-load-bearing by construction** -- it records *that* a hit / miss /
record / eviction happened, for `stats` and `prune` to read, but it never gates
correctness. Every operation swallows its own errors: if the database is missing,
locked, unwritable, or corrupt, the cache still resolves exactly as it would
without it. It is deliberately separate from the executions, which stay pure and
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

# The access events. A resolve emits exactly one of HIT / MISS / RECORD
# (passthrough calls are outside cache accounting and emit nothing).
HIT = "hit"
MISS = "miss"
RECORD = "record"

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
    """A best-effort SQLite log of access events, living beside the executions."""

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

    def hit_counts_by_key(self) -> Dict[str, int]:
        """Return {match_key: number-of-hits} across all recorded HIT events
        ({} if unavailable).

        A hit is a real call that was *not* made because a stored execution answered it,
        so multiplying an execution's recorded usage by its hit count is exactly the
        usage that hit saved. Best-effort like everything here: never raises.
        """
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT match_key, COUNT(*) FROM access_events "
                    "WHERE event = ? AND match_key IS NOT NULL GROUP BY match_key",
                    (HIT,),
                ).fetchall()
                return {key: int(count) for key, count in rows}
            finally:
                conn.close()
        except Exception:
            return {}

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

    def last_access(self) -> Dict[str, float]:
        """Return {match_key: latest-event epoch seconds} for LRU eviction ordering
        ({} if unavailable). An execution absent here has never been seen by the
        registry; the caller falls back to file age for it."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT match_key, MAX(ts) FROM access_events "
                    "WHERE match_key IS NOT NULL GROUP BY match_key"
                ).fetchall()
            finally:
                conn.close()
        except Exception:
            return {}
        out: Dict[str, float] = {}
        for key, ts in rows:
            try:
                out[key] = datetime.fromisoformat(ts).timestamp()
            except Exception:
                pass
        return out
