# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The access registry: a side log of cache access events for observability.

It is **non-load-bearing by construction** -- it records *that* a hit / miss /
record / eviction happened, for `stats` and `prune` to read, but it never gates
correctness. Every operation swallows its own errors: if the database is missing,
locked, unwritable, or corrupt, the cache still resolves exactly as it would
without it. It is deliberately separate from the executions, which stay pure and
immutable -- no access counters are ever written back into a recording.

Stored in the store directory as ``registry.sqlite3`` (stdlib ``sqlite3``). It
carries no integrity/checksum role: a checksum kept
beside the data it guards, in a folder the user can write, protects nothing a
determined editor couldn't also rewrite -- so we don't pretend to.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Every cache resolution appends one event; HIT is the one queried for hit-rate.
HIT = "hit"
MISS = "miss"
RECORD = "record"

_DB_NAME = "registry.sqlite3"
_SCHEMA = """
CREATE TABLE IF NOT EXISTS access_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    event      TEXT NOT NULL,
    match_key  TEXT,
    client     TEXT,
    model      TEXT,
    effort     TEXT,
    session_id TEXT
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
        self._ensure_session_column(conn)
        self._ensure_session_tags_table(conn)
        return conn

    @staticmethod
    def _ensure_session_column(conn: sqlite3.Connection) -> None:
        # Additive migration for registries created before sessions existed.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(access_events)")}
        if "session_id" not in columns:
            conn.execute("ALTER TABLE access_events ADD COLUMN session_id TEXT")
            conn.commit()

    @staticmethod
    def _ensure_session_tags_table(conn: sqlite3.Connection) -> None:
        # Additive migration for registries created before session tags existed.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_tags (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tag        TEXT NOT NULL
            )
            """
        )
        conn.commit()

    def record(
        self,
        event: str,
        *,
        match_key: Optional[str],
        client: str,
        model: str,
        effort: str,
        session_id: Optional[str] = None,
    ) -> None:
        """Append one access event. Never raises -- failures are swallowed so the
        cache is never affected by the registry being unavailable."""
        try:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO access_events "
                    "(ts, event, match_key, client, model, effort, session_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        event,
                        match_key,
                        client,
                        model,
                        effort,
                        session_id,
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

    def session_event_counts(self, session_id: str) -> Dict[str, int]:
        """Return {event: count} for one session ({} if unknown or unavailable)."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT event, COUNT(*) FROM access_events WHERE session_id = ? GROUP BY event",
                    (session_id,),
                ).fetchall()
                return {event: count for event, count in rows}
            finally:
                conn.close()
        except Exception:
            return {}

    def session_events(self, session_id: str) -> List[Tuple]:
        """Return (ts, event, client, model, match_key) rows for one session, oldest
        first ([] if unknown or unavailable)."""
        try:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT ts, event, client, model, match_key FROM access_events "
                    "WHERE session_id = ? ORDER BY id",
                    (session_id,),
                ).fetchall()
            finally:
                conn.close()
        except Exception:
            return []

    def execution_keys_for_session(self, session_id: str) -> List[str]:
        """Return the distinct execution keys (match_keys) recorded under
        ``session_id`` ([] if unknown or unavailable). Used by the purge service
        to collect every execution that belongs to a session."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT match_key FROM access_events "
                    "WHERE session_id = ? AND match_key IS NOT NULL",
                    (session_id,),
                ).fetchall()
                return [key for (key,) in rows]
            finally:
                conn.close()
        except Exception:
            return []

    def delete_events_for_key(self, execution_key: str) -> None:
        """Remove all access events for ``execution_key``. Called during a hard
        delete to erase the key's history from the registry. Non-load-bearing:
        failures are swallowed."""
        try:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM access_events WHERE match_key = ?",
                    (execution_key,),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def add_session_tag(self, session_id: str, tag: str) -> None:
        """Attach ``tag`` to ``session_id``. Duplicate tags are stored once per call;
        callers that want idempotency should check first. Non-load-bearing: never raises."""
        try:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO session_tags (session_id, tag) VALUES (?, ?)",
                    (session_id, tag),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def remove_session_tag(self, session_id: str, tag: str) -> None:
        """Detach ``tag`` from ``session_id``. No-op when the tag is absent. Never raises."""
        try:
            conn = self._connect()
            try:
                conn.execute(
                    "DELETE FROM session_tags WHERE session_id = ? AND tag = ?",
                    (session_id, tag),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def session_tags_for_id(self, session_id: str) -> List[str]:
        """Return the distinct tags attached to ``session_id`` ([] if unknown or unavailable)."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT tag FROM session_tags WHERE session_id = ? ORDER BY tag",
                    (session_id,),
                ).fetchall()
                return [tag for (tag,) in rows]
            finally:
                conn.close()
        except Exception:
            return []

    def session_ids_for_tag(self, tag: str) -> List[str]:
        """Return the distinct session ids carrying ``tag`` ([] if unknown or unavailable)."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT session_id FROM session_tags WHERE tag = ?",
                    (tag,),
                ).fetchall()
                return [session_id for (session_id,) in rows]
            finally:
                conn.close()
        except Exception:
            return []

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
