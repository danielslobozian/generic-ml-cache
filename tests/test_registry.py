# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The access registry records hit / miss / record events for observability, and
is non-load-bearing: if it cannot be written, the cache resolves exactly as it
would without it."""

from __future__ import annotations

import pytest

from generic_ml_cache import Mode, Request, resolve
from generic_ml_cache.access_registry import AccessRegistry
from generic_ml_cache.errors import CacheMiss


def req(prompt: str) -> Request:
    return Request(client="fake", model="m1", effort="high", context="ctx", prompt=prompt)


def test_miss_then_record_then_hit_are_logged(store):
    resolve(req("STDOUT hi"), store, mode=Mode.CACHE)  # not cached -> records
    resolve(req("STDOUT hi"), store, mode=Mode.CACHE)  # cached -> hit
    counts = store.registry.event_counts()
    assert counts.get("record") == 1
    assert counts.get("hit") == 1


def test_offline_miss_is_logged(store):
    with pytest.raises(CacheMiss):
        resolve(req("STDOUT nope"), store, mode=Mode.OFFLINE)
    assert store.registry.event_counts().get("miss") == 1


def test_passthrough_is_not_counted(store):
    # An allow-path call is non-cacheable; it runs fresh and is outside hit/miss
    # accounting, so it logs nothing.
    request = Request(
        client="fake",
        model="m1",
        effort="high",
        context="ctx",
        prompt="STDOUT hi",
        allow_paths=[str(store.root)],
    )
    out = resolve(request, store, mode=Mode.CACHE)
    assert out.passthrough is True
    assert store.registry.event_counts() == {}


def test_registry_is_non_load_bearing(store, monkeypatch):
    # Every registry write blows up, yet the cache resolves correctly.
    def _boom(self):
        raise RuntimeError("registry db is down")

    monkeypatch.setattr(AccessRegistry, "_connect", _boom)
    out = resolve(req("STDOUT hi"), store, mode=Mode.CACHE)
    assert out.recorded is True
    assert len(store) == 1
    hit = resolve(req("STDOUT hi"), store, mode=Mode.CACHE)
    assert hit.hit is True
