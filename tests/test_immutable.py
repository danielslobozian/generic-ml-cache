# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Cassettes are write-once and immutable: a saved cassette is read-only on disk,
a refresh can still replace it, and a cache hit never writes back into it."""

from __future__ import annotations

from generic_ml_cache import Mode, Request, resolve
from generic_ml_cache.application.domain.model.cassette import Cassette, Response

INPUT = {"context": "c", "prompt": "p"}


def req(prompt: str) -> Request:
    return Request(client="fake", model="m1", effort="high", context="ctx", prompt=prompt)


def is_readonly(path) -> bool:
    return (path.stat().st_mode & 0o222) == 0


def test_saved_cassette_is_read_only(store):
    path = store.save(Cassette("fake", "m1", "high", INPUT, Response(stdout="x")))
    assert is_readonly(path)


def test_refresh_can_replace_a_read_only_cassette(store):
    first = Cassette("fake", "m1", "high", INPUT, Response(stdout="v1"))
    path = store.save(first)
    assert is_readonly(path)

    # Same key, new content: saving again must overwrite the read-only file (the
    # write bit is cleared before the atomic replace) and re-freeze the result.
    store.save(Cassette("fake", "m1", "high", INPUT, Response(stdout="v2")))
    again = store.lookup("fake", "m1", "high", INPUT)
    assert again is not None and again.response.stdout == "v2"
    assert is_readonly(path)


def test_hit_never_writes_back_to_the_cassette(store):
    out = resolve(req("STDOUT hello"), store, mode=Mode.CACHE)
    path = store._path_for(out.cassette.match_key)
    before_bytes = path.read_bytes()
    before_mode = path.stat().st_mode

    hit = resolve(req("STDOUT hello"), store, mode=Mode.OFFLINE)
    assert hit.hit is True
    # The cassette is byte-for-byte unchanged: no access metadata leaks into it.
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mode == before_mode
