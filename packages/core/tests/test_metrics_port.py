# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for MetricsPort contract."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Optional

import pytest

from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort, SessionEventRow


class InMemoryMetrics(MetricsPort):
    """Minimal in-memory implementation used to verify the port contract."""

    def __init__(self) -> None:
        self._events: list = []

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
