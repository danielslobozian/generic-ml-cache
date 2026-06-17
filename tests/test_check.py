# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The read-only cache probe (the core behind `check`).

A probe answers "is this exact call already cached?" without launching a client,
writing a cassette, or logging an access event -- and it must agree with what a
real run would do, because it reuses run's own key and cacheability logic.
"""

from __future__ import annotations

from generic_ml_cache.cache import Mode, ProbeStatus, Request, probe, resolve


def _request(prompt: str = "hello", **kw) -> Request:
    return Request(client="fake", model="m", effort="high", context="", prompt=prompt, **kw)


def _cassette_count(store) -> int:
    return len(list(store.root.glob("*.json"))) if store.root.exists() else 0


def test_probe_reports_hit_for_a_recorded_call(store):
    request = _request("STDOUT recorded")
    recorded = resolve(request, store, mode=Mode.CACHE)  # fresh record
    assert recorded.recorded is True

    result = probe(request, store)
    assert result.status is ProbeStatus.HIT
    # The probe found the very cassette the run recorded -- same key, no drift.
    assert result.cassette is not None
    assert result.cassette.match_key == recorded.cassette.match_key


def test_probe_reports_miss_when_nothing_recorded(store):
    result = probe(_request("never recorded"), store)
    assert result.status is ProbeStatus.MISS
    assert result.cassette is None


def test_probe_reports_non_cacheable_for_allow_path_calls(store):
    # Declaring an allow-path folder makes a call non-cacheable (passthrough).
    request = _request("scan", allow_paths=["/tmp"])
    result = probe(request, store)
    assert result.status is ProbeStatus.NON_CACHEABLE
    assert result.cassette is None


def test_trust_scan_makes_an_allow_path_call_cacheable_again(store):
    # With scan-trust on, the same allow-path call is treated as cacheable, so the
    # probe does a real lookup (a miss here, since nothing is recorded).
    request = _request("scan", allow_paths=["/tmp"])
    result = probe(request, store, trust_scan=True)
    assert result.status is ProbeStatus.MISS


def test_probe_writes_nothing_and_logs_nothing(store):
    # Record exactly one call, then probe repeatedly.
    resolve(_request("STDOUT one"), store, mode=Mode.CACHE)
    before_count = _cassette_count(store)
    before_events = store.registry.event_counts()

    for _ in range(3):
        probe(_request("STDOUT one"), store)  # a hit
        probe(_request("absent"), store)  # a miss

    # No cassette created, and no access event recorded by the probe.
    assert _cassette_count(store) == before_count
    assert store.registry.event_counts() == before_events
