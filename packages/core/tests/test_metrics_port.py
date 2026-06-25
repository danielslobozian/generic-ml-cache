# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for MetricsPort contract."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

import pytest

from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort, SessionEventRow


class InMemoryMetrics(MetricsPort):
    """Minimal in-memory implementation used to verify the port contract."""

    def __init__(self) -> None:
        self._events: list = []
        self._session_tags: Dict[str, List[str]] = {}

    def record_event(
        self,
        event: str,
        *,
        execution_key: Optional[str],
        client: str,
        model: str,
        effort: str,
        session_id: Optional[str] = None,
    ) -> None:
        self._events.append(
            {
                "event": event,
                "execution_key": execution_key,
                "client": client,
                "model": model,
                "effort": effort,
                "session_id": session_id,
            }
        )

    def hit_counts_by_key(self) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for recorded_event in self._events:
            if recorded_event["event"] == "hit" and recorded_event["execution_key"]:
                counts[recorded_event["execution_key"]] += 1
        return dict(counts)

    def event_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for recorded_event in self._events:
            counts[recorded_event["event"]] += 1
        return dict(counts)

    def session_event_counts(self, session_id: str) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for recorded_event in self._events:
            if recorded_event["session_id"] == session_id:
                counts[recorded_event["event"]] += 1
        return dict(counts)

    def session_events(self, session_id: str):
        return [
            SessionEventRow(
                ts="",
                event=e["event"],
                client=e["client"],
                model=e["model"],
                execution_key=e["execution_key"],
            )
            for e in self._events
            if e["session_id"] == session_id
        ]

    def last_access(self) -> Dict[str, float]:
        return {}

    def execution_keys_for_session(self, session_id: str):
        return list(
            {
                e["execution_key"]
                for e in self._events
                if e["session_id"] == session_id and e["execution_key"] is not None
            }
        )

    def delete_events_for_key(self, execution_key: str) -> None:
        self._events = [e for e in self._events if e["execution_key"] != execution_key]

    def add_session_tag(self, session_id: str, tag: str) -> None:
        self._session_tags.setdefault(session_id, []).append(tag)

    def remove_session_tag(self, session_id: str, tag: str) -> None:
        tags = self._session_tags.get(session_id, [])
        if tag in tags:
            tags.remove(tag)

    def session_tags(self, session_id: str) -> List[str]:
        return list(dict.fromkeys(self._session_tags.get(session_id, [])))

    def session_ids_for_tag(self, tag: str) -> List[str]:
        return list(dict.fromkeys(sid for sid, tags in self._session_tags.items() if tag in tags))


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        MetricsPort()  # type: ignore[abstract]


def test_record_event_appends_event():
    metrics = InMemoryMetrics()
    metrics.record_event(
        "hit", execution_key="key1", client="claude", model="sonnet", effort="high"
    )
    assert metrics.event_counts() == {"hit": 1}


def test_hit_counts_by_key_counts_hits():
    metrics = InMemoryMetrics()
    metrics.record_event("hit", execution_key="key1", client="claude", model="sonnet", effort="")
    metrics.record_event("hit", execution_key="key1", client="claude", model="sonnet", effort="")
    metrics.record_event("hit", execution_key="key2", client="claude", model="sonnet", effort="")
    counts = metrics.hit_counts_by_key()
    assert counts["key1"] == 2
    assert counts["key2"] == 1


def test_event_counts_groups_by_event_name():
    metrics = InMemoryMetrics()
    metrics.record_event("hit", execution_key="k1", client="c", model="m", effort="")
    metrics.record_event("record", execution_key="k2", client="c", model="m", effort="")
    metrics.record_event("hit", execution_key="k3", client="c", model="m", effort="")
    counts = metrics.event_counts()
    assert counts["hit"] == 2
    assert counts["record"] == 1


def test_empty_metrics_returns_empty_dicts():
    metrics = InMemoryMetrics()
    assert metrics.hit_counts_by_key() == {}
    assert metrics.event_counts() == {}
    assert metrics.last_access() == {}


def test_record_event_accepts_none_execution_key():
    metrics = InMemoryMetrics()
    metrics.record_event("miss", execution_key=None, client="claude", model="sonnet", effort="")
    assert metrics.event_counts() == {"miss": 1}


# --- session tags ------------------------------------------------------------


def test_session_tags_empty_for_unknown_session():
    assert InMemoryMetrics().session_tags("no-such-session") == []


def test_session_ids_for_tag_empty_when_no_sessions_tagged():
    assert InMemoryMetrics().session_ids_for_tag("anything") == []


def test_add_session_tag_and_retrieve():
    metrics = InMemoryMetrics()
    metrics.add_session_tag("s1", "feature-x")
    assert metrics.session_tags("s1") == ["feature-x"]


def test_multiple_tags_on_one_session():
    metrics = InMemoryMetrics()
    metrics.add_session_tag("s1", "alpha")
    metrics.add_session_tag("s1", "beta")
    assert set(metrics.session_tags("s1")) == {"alpha", "beta"}


def test_session_ids_for_tag_returns_all_matching_sessions():
    metrics = InMemoryMetrics()
    metrics.add_session_tag("s1", "ticket-001")
    metrics.add_session_tag("s2", "ticket-001")
    metrics.add_session_tag("s3", "other")
    assert set(metrics.session_ids_for_tag("ticket-001")) == {"s1", "s2"}


def test_session_ids_for_tag_deduplicates():
    metrics = InMemoryMetrics()
    metrics.add_session_tag("s1", "t")
    metrics.add_session_tag("s1", "t")
    assert metrics.session_ids_for_tag("t") == ["s1"]


def test_session_tags_are_isolated_per_session():
    metrics = InMemoryMetrics()
    metrics.add_session_tag("s1", "x")
    metrics.add_session_tag("s2", "y")
    assert metrics.session_tags("s1") == ["x"]
    assert metrics.session_tags("s2") == ["y"]
