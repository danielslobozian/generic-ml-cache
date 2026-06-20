# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""A failed client call (non-zero exit) is not cached by default; ``record_on_error``
opts into caching it, and a failing refresh never overwrites a good recording."""

from __future__ import annotations

from generic_ml_cache import Mode, Request, resolve
from generic_ml_cache.application.domain.model.cassette import Cassette, Response

# The fake client prints, then exits 1 (a real failure that still produced output).
FAILING = "STDOUT partial output\nEXIT 1"
OK = "STDOUT all good"


def req(prompt: str) -> Request:
    return Request(client="fake", model="m1", effort="high", context="ctx", prompt=prompt)


def test_failed_call_is_not_cached_by_default(store):
    out = resolve(req(FAILING), store, mode=Mode.CACHE)
    # The real failed response is still handed back to the caller...
    assert out.response.exit == 1
    assert "partial output" in out.response.stdout
    # ...but nothing is stored, and it is flagged as a deliberate non-store.
    assert out.failed_unstored is True
    assert out.recorded is False and out.hit is False
    assert len(store) == 0


def test_failed_call_runs_fresh_again_never_a_hit(store):
    resolve(req(FAILING), store, mode=Mode.CACHE)
    second = resolve(req(FAILING), store, mode=Mode.CACHE)
    # No cassette was ever written, so the second identical call cannot be a hit.
    assert second.hit is False
    assert second.failed_unstored is True
    assert len(store) == 0


def test_record_on_error_caches_the_failure(store):
    out = resolve(req(FAILING), store, mode=Mode.CACHE, record_on_error=True)
    assert out.recorded is True and out.failed_unstored is False
    assert len(store) == 1
    # It now replays as a hit, reproducing the failure exactly.
    replay = resolve(req(FAILING), store, mode=Mode.OFFLINE)
    assert replay.hit is True
    assert replay.response.exit == 1
    assert "partial output" in replay.response.stdout


def test_successful_call_is_cached_by_default(store):
    out = resolve(req(OK), store, mode=Mode.CACHE)
    assert out.recorded is True and out.failed_unstored is False
    assert out.response.exit == 0
    assert len(store) == 1


def test_failing_refresh_leaves_existing_success_untouched(store):
    # Seed a SUCCESS cassette under the exact key the failing request computes.
    request = req(FAILING)
    good = Cassette(
        client=request.client,
        model=request.model,
        effort=request.effort,
        input_data=request.input_data,
        response=Response(stdout="GOOD RECORDING\n", exit=0),
    )
    store.save(good)
    assert len(store) == 1

    # A refresh calls the real client, which fails; the default policy must not
    # overwrite the good recording with that failure.
    out = resolve(request, store, mode=Mode.REFRESH)
    assert out.failed_unstored is True and out.recorded is False
    survivor = store.lookup(request.client, request.model, request.effort, request.input_data)
    assert survivor is not None
    assert survivor.response.exit == 0
    assert survivor.response.stdout == "GOOD RECORDING\n"
