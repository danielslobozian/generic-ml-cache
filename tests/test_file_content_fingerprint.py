# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared file_content_fingerprint rule."""

from __future__ import annotations

import hashlib

from generic_ml_cache import file_content_fingerprint


def test_is_plain_sha256_of_raw_bytes():
    assert file_content_fingerprint(b"hello") == hashlib.sha256(b"hello").hexdigest()


def test_is_deterministic():
    assert file_content_fingerprint(b"data") == file_content_fingerprint(b"data")


def test_different_content_different_fingerprint():
    assert file_content_fingerprint(b"a") != file_content_fingerprint(b"b")


def test_returns_64_char_hex():
    fingerprint = file_content_fingerprint(b"anything")
    assert len(fingerprint) == 64
    assert all(char in "0123456789abcdef" for char in fingerprint)


def test_empty_bytes_have_a_stable_fingerprint():
    assert file_content_fingerprint(b"") == hashlib.sha256(b"").hexdigest()


def test_binary_safe_handles_non_utf8_bytes():
    invalid_utf8 = b"\xff\xfe\x00\x01"
    assert file_content_fingerprint(invalid_utf8) == hashlib.sha256(invalid_utf8).hexdigest()


def test_matches_the_inline_rule_the_cli_used():
    """The CLI fingerprinted input files with hashlib.sha256(data).hexdigest();
    the shared rule must produce byte-for-byte the same digest so existing keys
    are preserved when the CLI switches to it."""
    sample = b"some file content\nwith a second line\n"
    assert file_content_fingerprint(sample) == hashlib.sha256(sample).hexdigest()
