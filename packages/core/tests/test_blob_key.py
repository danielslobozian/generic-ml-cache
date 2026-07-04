# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the BlobKey value object (C-5, V14 traversal defense)."""

from __future__ import annotations

import hashlib

import pytest

from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey

_FINGERPRINT = hashlib.sha256(b"x").hexdigest()  # a real 64-char content key


def test_accepts_a_content_fingerprint():
    key = BlobKey(_FINGERPRINT)
    assert key == _FINGERPRINT
    assert isinstance(key, str)  # drop-in wherever a key string is used


def test_accepts_a_suffixed_key():
    # The charset permits a dotted suffix on a content fingerprint.
    assert BlobKey(f"{_FINGERPRINT}.bin") == f"{_FINGERPRINT}.bin"


def test_accepts_plain_names_with_dots_hyphens_underscores():
    for value in ("a", "a.b", "a-b_c.d", "..req", "v1.2.3"):
        assert BlobKey(value) == value


@pytest.mark.parametrize(
    "bad",
    [
        "",  # empty
        ".",  # current dir
        "..",  # parent dir
        "a/b",  # path separator
        "../evil",  # traversal
        "/abs",  # absolute
        "a\\b",  # windows separator
        "a b",  # whitespace
        "a\x00b",  # null byte
        "a\nb",  # newline / control
        "x" * 256,  # too long
    ],
)
def test_rejects_unsafe_keys(bad):
    with pytest.raises(ValueError, match="invalid blob key"):
        BlobKey(bad)


def test_is_usable_as_a_path_component():
    from pathlib import PurePosixPath

    root = PurePosixPath("/store/blobs")
    key = BlobKey(_FINGERPRINT)
    resolved = root / key
    # Stays under the root — no traversal.
    assert str(resolved) == f"/store/blobs/{_FINGERPRINT}"
