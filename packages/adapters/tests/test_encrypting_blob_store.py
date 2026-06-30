# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for EncryptingBlobStore / TokenRequiredBlobStore."""

from __future__ import annotations

import pytest

pytest.importorskip("cryptography")  # the optional [encryption] extra

from generic_ml_cache_core.common.errors import (  # noqa: E402
    EncryptionTokenRequired,
    WrongEncryptionToken,
)

from generic_ml_cache_adapters.adapter.out.crypto.aesgcm_cipher import AesGcmCipher  # noqa: E402
from generic_ml_cache_adapters.adapter.out.crypto.encrypting_blob_store import (  # noqa: E402
    EncryptingBlobStore,
    TokenRequiredBlobStore,
)
from generic_ml_cache_adapters.adapter.out.storage.filesystem_blob_store import (  # noqa: E402
    FilesystemBlobStore,
)


def _encrypting(tmp_path):
    inner = FilesystemBlobStore(tmp_path / "blobs")
    cipher = AesGcmCipher()
    _, data_key = cipher.create_envelope(cipher.generate_token())
    return EncryptingBlobStore(inner, cipher, data_key), inner, cipher


def test_put_then_get_round_trips(tmp_path):
    store, *_ = _encrypting(tmp_path)
    store.put("k", b"secret content")
    assert store.get("k") == b"secret content"


def test_bytes_on_disk_are_ciphertext(tmp_path):
    store, inner, _ = _encrypting(tmp_path)
    store.put("k", b"SECRETMARKER-xyz")
    raw = inner.get("k")  # what is actually persisted, unwrapped by nobody
    assert raw is not None
    assert raw != b"SECRETMARKER-xyz"
    assert b"SECRETMARKER-xyz" not in raw


def test_get_missing_is_none(tmp_path):
    store, *_ = _encrypting(tmp_path)
    assert store.get("nope") is None


def test_a_different_key_cannot_decrypt(tmp_path):
    store, inner, cipher = _encrypting(tmp_path)
    store.put("k", b"secret")
    _, other_key = cipher.create_envelope(cipher.generate_token())
    with pytest.raises(WrongEncryptionToken):
        EncryptingBlobStore(inner, cipher, other_key).get("k")


def test_token_required_blocks_content_but_allows_remove(tmp_path):
    inner = FilesystemBlobStore(tmp_path / "blobs")
    inner.put("k", b"ciphertext-on-disk")
    locked = TokenRequiredBlobStore(inner)
    with pytest.raises(EncryptionTokenRequired):
        locked.get("k")
    with pytest.raises(EncryptionTokenRequired):
        locked.put("k", b"x")
    locked.remove("k")  # keyless, allowed through
    assert inner.get("k") is None
