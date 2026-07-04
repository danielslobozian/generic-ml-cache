# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for EncryptingBlobStore / TokenRequiredBlobStore."""

from __future__ import annotations

import pytest

pytest.importorskip("cryptography")  # the optional [encryption] extra

from generic_ml_cache_core.common.errors import (  # noqa: E402
    EncryptionTokenRequired,
    StoreCorrupt,
)

from generic_ml_cache_adapters.adapter.outbound.crypto.aesgcm_cipher import (
    AesGcmCipher,  # noqa: E402
)
from generic_ml_cache_adapters.adapter.outbound.crypto.encrypting_blob_store import (  # noqa: E402
    EncryptingBlobStore,
    TokenRequiredBlobStore,
)
from generic_ml_cache_adapters.adapter.outbound.storage.filesystem_blob_store import (  # noqa: E402
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


def test_corrupt_ciphertext_with_a_valid_key_surfaces_as_store_corrupt(tmp_path):
    # The data key already opened the envelope (verified at wiring), so a content
    # decrypt failure means the stored blob is corrupt, not a wrong token. It must
    # surface as StoreCorrupt so the serve path self-heals (S5c → S4).
    store, inner, _ = _encrypting(tmp_path)
    store.put("k", b"secret")
    inner.put("k", b"tampered-not-valid-ciphertext")  # corrupt the stored bytes
    with pytest.raises(StoreCorrupt):
        store.get("k")


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


def test_token_required_gate_fails_fast_at_entry(tmp_path):
    # The S5a up-front gate: a content op fails here, before any client call.
    locked = TokenRequiredBlobStore(FilesystemBlobStore(tmp_path / "blobs"))
    with pytest.raises(EncryptionTokenRequired):
        locked.ensure_available_for_content()


def test_available_stores_pass_the_gate(tmp_path):
    # A plain or token-opened store needs no token — the gate is a no-op.
    FilesystemBlobStore(tmp_path / "blobs").ensure_available_for_content()
    store, *_ = _encrypting(tmp_path)
    store.ensure_available_for_content()
