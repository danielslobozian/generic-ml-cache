# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Input files: content-fingerprinted, declared read access (0.0.4)."""

from __future__ import annotations

import hashlib

import pytest

from generic_ml_cache import CacheMiss, Mode, Request, resolve
from generic_ml_cache import config
from generic_ml_cache.common.checksum import checksum_input_data
from generic_ml_cache.cli import main
from generic_ml_cache.common.prime_directive import build_system_prompt


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _req(input_files):
    return Request(
        client="fake",
        model="m",
        effort="",
        context="ctx",
        prompt="STDOUT hi",
        input_files=input_files,
    )


# --- keying: content only, order- and name-independent ---------------------


def test_fingerprint_enters_input_data():
    sha = _sha(b"hello")
    r = _req({"/some/path.txt": sha})
    assert r.input_data[f"input_file:{sha}"] == sha
    assert "context" in r.input_data and "prompt" in r.input_data


def test_same_content_different_path_is_same_key():
    sha = _sha(b"same bytes")
    a = _req({"/a/one.txt": sha})
    b = _req({"/b/two.txt": sha})
    assert checksum_input_data(a.input_data) == checksum_input_data(b.input_data)


def test_content_change_changes_key():
    a = _req({"/p.txt": _sha(b"v1")})
    b = _req({"/p.txt": _sha(b"v2")})
    assert checksum_input_data(a.input_data) != checksum_input_data(b.input_data)


def test_order_independent():
    s1, s2 = _sha(b"one"), _sha(b"two")
    a = _req({"/a": s1, "/b": s2})
    b = _req({"/b": s2, "/a": s1})
    assert checksum_input_data(a.input_data) == checksum_input_data(b.input_data)


def test_identical_content_dedups_to_one_entry():
    sha = _sha(b"dup")
    r = _req({"/a": sha, "/b": sha})  # two paths, same content
    keys = [k for k in r.input_data if k.startswith("input_file:")]
    assert keys == [f"input_file:{sha}"]


def test_no_input_files_unchanged_key():
    # a call with no input files keys exactly as before the feature existed
    r = _req({})
    assert set(r.input_data) == {"context", "prompt"}


# --- the door: declared paths widen the prime directive --------------------


def test_door_lists_allowed_paths_in_system_prompt():
    sp = build_system_prompt(None, allowed_read_paths=["/data/schema.sql"])
    assert "/data/schema.sql" in sp
    assert "READ" in sp and "DECLARED READ PATHS" in sp


def test_door_absent_when_no_paths():
    sp = build_system_prompt(None)
    assert "DECLARED INPUT FILES" not in sp
    assert "PRIME DIRECTIVE" in sp  # baseline directive still present


def test_allowed_read_paths_sorted():
    r = _req({"/z/b.txt": _sha(b"b"), "/a/a.txt": _sha(b"a")})
    assert r.allowed_read_paths == ["/a/a.txt", "/z/b.txt"]


# --- end to end through the fake client ------------------------------------


def test_record_then_hit_then_miss_on_content_change(store, tmp_path):
    f = tmp_path / "in.txt"
    f.write_bytes(b"alpha")
    req = _req({str(f): _sha(b"alpha")})

    first = resolve(req, store, mode=Mode.CACHE)
    assert first.recorded and not first.hit

    # same content -> served offline (hit), no new cassette
    out = resolve(req, store, mode=Mode.OFFLINE)
    assert out.hit and len(store) == 1

    # changed content -> different key -> offline miss
    changed = _req({str(f): _sha(b"beta")})
    with pytest.raises(CacheMiss):
        resolve(changed, store, mode=Mode.OFFLINE)


# --- CLI ergonomics --------------------------------------------------------


def test_cli_missing_input_file_errors(tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "--client",
                "fake",
                "--model",
                "m",
                "--prompt",
                "STDOUT hi",
                "--input-file",
                str(tmp_path / "nope.txt"),
            ]
        )


def test_cli_run_with_input_file_records(tmp_path):
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02 any bytes, not text")  # any file type
    rc = main(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m",
            "--prompt",
            "STDOUT hi",
            "--input-file",
            str(f),
        ]
    )
    assert rc == 0
    assert list(config.default_store_path().glob("*.json"))  # a cassette was written
