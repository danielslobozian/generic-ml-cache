# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Opt-in size+idle eviction: off by default, and when a cap is set the cache
evicts least-recently-used cassettes to make room on insert -- but never drops the
fresh result it was asked to store (soft cap)."""

from __future__ import annotations

from generic_ml_cache.adapter.out.storage.store import CassetteStore
from generic_ml_cache.application.domain.model.cassette import Cassette, Response

PAD = "x" * 1000  # make each cassette ~1 KB so sizing is predictable


def cas(tag: str) -> Cassette:
    return Cassette("fake", "m", "e", {"context": "c", "prompt": tag}, Response(stdout=PAD))


def keys_on_disk(store: CassetteStore):
    return {p.stem for p in store.root.glob("*.json")}


def test_off_by_default_keeps_everything(tmp_path):
    store = CassetteStore(tmp_path / "cas")  # no cap
    for tag in "ABCDEF":
        store.save(cas(tag))
    assert len(store) == 6  # nothing evicted


def test_soft_cap_never_drops_the_fresh_result(tmp_path):
    # Cap smaller than a single cassette: it still gets stored (overshoot), because
    # we never throw away the call we were just asked to record.
    store = CassetteStore(tmp_path / "cas", max_bytes=10)
    store.save(cas("A"))
    assert len(store) == 1


def test_eviction_drops_least_recently_used_to_fit(tmp_path):
    one = len(cas("A").to_json().encode("utf-8"))
    # Room for ~two cassettes, not three.
    store = CassetteStore(tmp_path / "cas", max_bytes=one * 2 + one // 2)

    a, b, c = cas("A"), cas("B"), cas("C")
    store.save(a)
    store.save(b)
    assert keys_on_disk(store) == {a.match_key, b.match_key}

    # Stamp explicit access times: A used recently, B long ago -> B is the idlest.
    conn = store.registry._connect()
    conn.execute(
        "INSERT INTO access_events (ts, event, match_key, client, model, effort) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("2026-06-17T18:00:00", "hit", a.match_key, "fake", "m", "e"),
    )
    conn.execute(
        "INSERT INTO access_events (ts, event, match_key, client, model, effort) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("2026-01-01T00:00:00", "record", b.match_key, "fake", "m", "e"),
    )
    conn.commit()
    conn.close()

    # Saving C forces eviction of the idlest (B); A and C survive.
    store.save(c)
    survivors = keys_on_disk(store)
    assert a.match_key in survivors
    assert c.match_key in survivors
    assert b.match_key not in survivors
    assert store.registry.event_counts().get("evict") == 1
