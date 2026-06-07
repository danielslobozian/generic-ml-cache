# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The checksum invariant is the heart of the cache, so it gets the most care."""

from __future__ import annotations

import json

from generic_ml_cache import checksum_input_data, text_checksum


def test_same_text_same_checksum_regardless_of_container(tmp_path):
    """Identical text yields the same checksum whether it came from a file or
    from inside a JSON string -- the container must not matter."""
    text = "line one\n\tindented line\nline three\n"

    # 1) text living in a standalone file
    f = tmp_path / "ctx.txt"
    f.write_text(text, encoding="utf-8")
    from_file = f.read_text(encoding="utf-8")

    # 2) the same text embedded inside a JSON document
    doc = json.dumps({"context": text})
    from_json = json.loads(doc)["context"]

    assert from_file == from_json == text
    assert checksum_input_data({"context": from_file, "prompt": "p"}) == checksum_input_data(
        {"context": from_json, "prompt": "p"}
    )


def test_newlines_and_tabs_are_significant():
    assert checksum_input_data({"context": "a\nb", "prompt": ""}) != checksum_input_data(
        {"context": "ab", "prompt": ""}
    )
    assert checksum_input_data({"context": "a\tb", "prompt": ""}) != checksum_input_data(
        {"context": "a b", "prompt": ""}
    )
    # trailing newline matters
    assert checksum_input_data({"context": "x", "prompt": ""}) != checksum_input_data(
        {"context": "x\n", "prompt": ""}
    )


def test_field_boundary_is_unambiguous():
    """('ab','c') must not collide with ('a','bc')."""
    assert checksum_input_data({"context": "ab", "prompt": "c"}) != checksum_input_data(
        {"context": "a", "prompt": "bc"}
    )


def test_key_order_does_not_matter():
    a = checksum_input_data({"context": "x", "prompt": "y"})
    b = checksum_input_data({"prompt": "y", "context": "x"})
    assert a == b


def test_text_checksum_is_plain_sha256_of_utf8():
    import hashlib

    assert text_checksum("hello") == hashlib.sha256(b"hello").hexdigest()
