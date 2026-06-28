# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The access registry: a side log of cache access events for observability.

It is **non-load-bearing by construction** -- it records *that* a hit / miss /
record / eviction happened, for `stats` and `prune` to read, but it never gates
correctness. Every operation swallows its own errors: if the database is missing,
locked, unwritable, or corrupt, the cache still resolves exactly as it would
without it. Schema is owned by the yoyo migration ``0001.unified-schema``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.out.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_core.common.db import DbConnection

# Every cache resolution appends one event; HIT is the one queried for hit-rate.
HIT = "hit"
MISS = "miss"
RECORD = "record"


class AccessRegistry:
    """A best-effort log of cache access events in the unified gmlcache database."""

    def __init__(
        self,
        conn_factory: Callable[[], DbConnection],
        diag: Optional[DiagnosticsPort] = None,
    ) -> None:
        self._conn_factory = conn_factory
        self._diag: DiagnosticsPort = diag if diag is not None else NullDiagnosticsAdapter()

    def _connect(self) -> DbConnection:
        return self._conn_factory()

    def _warn_db_error(self, operation: str, exc: Exception) -> None:
        self._diag.warn(f"access registry DB error — {operation}", exc=exc)

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
        except Exception as exc:
            self._warn_db_error("record event", exc)

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
        except Exception as exc:
            self._warn_db_error("hit_counts_by_key", exc)
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
        except Exception as exc:
            self._warn_db_error("event_counts", exc)
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
        except Exception as exc:
            self._warn_db_error("session_event_counts", exc)
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
        except Exception as exc:
            self._warn_db_error("session_events", exc)
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
        except Exception as exc:
            self._warn_db_error("execution_keys_for_session", exc)
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
        except Exception as exc:
            self._warn_db_error("delete_events_for_key", exc)

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
        except Exception as exc:
            self._warn_db_error("add_session_tag", exc)

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
        except Exception as exc:
            self._warn_db_error("remove_session_tag", exc)

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
        except Exception as exc:
            self._warn_db_error("session_tags_for_id", exc)
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
        except Exception as exc:
            self._warn_db_error("session_ids_for_tag", exc)
            return []

    def set_session_spec(self, session_id: str, spec: SessionSpec) -> None:
        """Upsert the execution spec for ``session_id``. Never raises."""
        try:
            conn = self._connect()
            try:
                cursor = conn.execute(
                    "UPDATE session_specs SET client=?, model=?, effort=? WHERE session_id=?",
                    (spec.client, spec.model, spec.effort, session_id),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        "INSERT INTO session_specs (session_id, client, model, effort) "
                        "SELECT ?, ?, ?, ? WHERE NOT EXISTS "
                        "(SELECT 1 FROM session_specs WHERE session_id = ?)",
                        (session_id, spec.client, spec.model, spec.effort, session_id),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            self._warn_db_error("set_session_spec", exc)

    def clear_session_spec(self, session_id: str) -> None:
        """Remove the execution spec for ``session_id``. No-op if absent. Never raises."""
        try:
            conn = self._connect()
            try:
                conn.execute("DELETE FROM session_specs WHERE session_id = ?", (session_id,))
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:
            self._warn_db_error("clear_session_spec", exc)

    def session_spec_for_id(self, session_id: str) -> Optional[SessionSpec]:
        """Return the execution spec for ``session_id``, or None if unset."""
        try:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT client, model, effort FROM session_specs WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                return SessionSpec(client=row[0], model=row[1], effort=row[2]) if row else None
            finally:
                conn.close()
        except Exception as exc:
            self._warn_db_error("session_spec_for_id", exc)
            return None

    def list_session_ids(self) -> List[str]:
        """Return all known session IDs, unioned across events, tags, and specs tables."""
        try:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT DISTINCT session_id FROM access_events WHERE session_id IS NOT NULL "
                    "UNION SELECT session_id FROM session_tags "
                    "UNION SELECT session_id FROM session_specs"
                ).fetchall()
                return [row[0] for row in rows]
            finally:
                conn.close()
        except Exception as exc:
            self._warn_db_error("list_session_ids", exc)
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
        except Exception as exc:
            self._warn_db_error("last_access", exc)
            return {}
        out: Dict[str, float] = {}
        for key, ts in rows:
            try:
                out[key] = datetime.fromisoformat(ts).timestamp()
            except Exception as exc:
                self._diag.debug("last_access: skipping unparseable timestamp", key=key, exc=exc)
        return out
