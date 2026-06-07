# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest

from generic_ml_cache import (
    CacheMiss,
    Mode,
    Request,
    apply_response,
    resolve,
)
from conftest import write_directive


def base_request(prompt: str, context: str = "ctx") -> Request:
    return Request(client="fake", model="m1", effort="high", context=context, prompt=prompt)


# --- modes -----------------------------------------------------------------


def test_offline_miss_is_an_error(store):
    with pytest.raises(CacheMiss):
        resolve(base_request("STDOUT hi"), store, mode=Mode.OFFLINE)


def test_cache_miss_records_then_hit_replays(store):
    req = base_request("STDOUT hi")
    first = resolve(req, store, mode=Mode.CACHE)
    assert first.recorded and not first.hit
    assert len(store) == 1

    second = resolve(req, store, mode=Mode.CACHE)
    assert second.hit and not second.recorded
    assert second.response.stdout == first.response.stdout
    assert len(store) == 1  # no new cassette


def test_offline_hit_after_record(store):
    req = base_request("STDOUT hi")
    resolve(req, store, mode=Mode.CACHE)  # populate
    out = resolve(req, store, mode=Mode.OFFLINE)
    assert out.hit
    assert "FINGERPRINT" in out.response.stdout


def test_refresh_always_calls_and_overwrites(store):
    req = base_request("STDOUT hi")
    resolve(req, store, mode=Mode.CACHE)
    out = resolve(req, store, mode=Mode.REFRESH)
    assert out.recorded and not out.hit
    assert len(store) == 1  # same key, overwritten


def test_distinct_effort_is_a_distinct_key(store):
    resolve(Request("fake", "m1", "high", "ctx", "STDOUT hi"), store)
    resolve(Request("fake", "m1", "low", "ctx", "STDOUT hi"), store)
    assert len(store) == 2


# --- capture / isolation ---------------------------------------------------


def test_client_files_are_captured(store):
    req = base_request(write_directive("sub/result.txt", "payload\n"))
    out = resolve(req, store, mode=Mode.CACHE)
    paths = {f.path for f in out.response.files}
    assert "sub/result.txt" in paths  # POSIX-style, portable


def test_input_files_are_not_captured_as_output(store):
    """The adapter's _in_*.txt scaffolding must never leak into the cassette."""
    req = base_request("STDOUT hi")
    out = resolve(req, store, mode=Mode.CACHE)
    captured = {f.path for f in out.response.files}
    assert not any(p.startswith("_in_") for p in captured)


def test_exit_code_and_streams_captured(store):
    prompt = "STDOUT hello\nSTDERR oops\nEXIT 7"
    out = resolve(base_request(prompt), store, mode=Mode.CACHE)
    assert out.response.exit == 7
    assert "hello" in out.response.stdout
    assert "oops" in out.response.stderr


# --- replay applies effects ------------------------------------------------


def test_replay_writes_files_into_output_dir(store, tmp_path):
    req = base_request(write_directive("nested/out.txt", "content-here\n"))
    out = resolve(req, store, mode=Mode.CACHE)

    dest = tmp_path / "caller"
    apply_response(out.response, dest)
    assert (dest / "nested" / "out.txt").read_text(encoding="utf-8") == "content-here\n"


def test_replay_is_byte_identical_to_record(store, tmp_path):
    req = base_request(write_directive("a.txt", "same\n"))
    recorded = resolve(req, store, mode=Mode.CACHE)
    replayed = resolve(req, store, mode=Mode.OFFLINE)
    assert recorded.response.stdout == replayed.response.stdout
    assert recorded.response.stderr == replayed.response.stderr
    assert recorded.response.exit == replayed.response.exit
    assert [f.to_dict() for f in recorded.response.files] == [
        f.to_dict() for f in replayed.response.files
    ]


def test_apply_refuses_path_escape(store, tmp_path):
    from generic_ml_cache import CapturedFile, Response

    bad = Response(files=[CapturedFile("../escape.txt", "nope")])
    with pytest.raises(ValueError):
        apply_response(bad, tmp_path / "out")


# --- prime directive -------------------------------------------------------


def test_prime_directive_makes_compliant_client_refuse_escape(store):
    req = base_request("OUTSIDE /etc/passwd")
    out = resolve(req, store, mode=Mode.CACHE)
    assert out.response.exit == 9
    assert "refusing" in out.response.stderr
    assert out.response.files == []  # nothing written
