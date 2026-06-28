# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for StoreEncryptor (enable/disable/rotate/invalidate + crash recovery)."""

from __future__ import annotations

import sqlite3
import pytest

pytest.importorskip("cryptography")

from generic_ml_cache_cli._compose import build_use_cases  # noqa: E402
from generic_ml_cache_adapters.adapter.out.crypto.aesgcm_cipher import AesGcmCipher  # noqa: E402
from generic_ml_cache_adapters.adapter.out.crypto.filesystem_encryption_manifest_store import (  # noqa: E402
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_adapters.adapter.out.crypto.store_encryptor import StoreEncryptor  # noqa: E402
from generic_ml_cache_adapters.adapter.out.persistence.filesystem_store_lock import (  # noqa: E402
    FilesystemStoreLock,
)
from generic_ml_cache_adapters.adapter.out.storage.filesystem_blob_store import (  # noqa: E402
    FilesystemBlobStore,
)
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (  # noqa: E402
    EncryptionState,
)
from generic_ml_cache_core.common.errors import (  # noqa: E402
    EncryptionStateError,
    WrongEncryptionToken,
)

_MARKER = "encryption.committing.json"


def _seed(store, items):
    blobs = FilesystemBlobStore(store / "blobs")
    for key, value in items.items():
        blobs.put(key, value)


def _encryptor(store):
    return StoreEncryptor(
        store, FilesystemEncryptionManifestStore(store), FilesystemStoreLock(store), AesGcmCipher()
    )


def _state(store):
    return FilesystemEncryptionManifestStore(store).state()


def _token():
    return AesGcmCipher().generate_token()


def _db_factory(store):
    db_path = store / "executions.sqlite3"

    def _connect():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(db_path))

    return _connect


def _read_decrypted(store, token, key):
    return build_use_cases(_db_factory(store), store, encryption_token=token).blob_store.get(key)


def _raw(store, key):
    return (store / "blobs" / key).read_bytes()


# --- enable / disable --------------------------------------------------------


def test_enable_encrypts_blobs_and_flips_state(tmp_path):
    store = tmp_path / "store"
    _seed(store, {"k1": b"one", "k2": b"PLAINMARKER-two"})
    token = _token()
    _encryptor(store).enable(token)

    assert _state(store) is EncryptionState.ENCRYPTED
    assert b"PLAINMARKER-two" not in _raw(store, "k2")  # ciphertext on disk
    assert _read_decrypted(store, token, "k2") == b"PLAINMARKER-two"  # decrypts with token


def test_enable_then_disable_round_trips_byte_identical(tmp_path):
    store = tmp_path / "store"
    items = {"k1": b"one", "k2": b"two PLAINMARKER"}
    _seed(store, items)
    token = _token()
    enc = _encryptor(store)
    enc.enable(token)
    enc.disable(token)

    assert _state(store) is EncryptionState.PUBLIC
    blobs = FilesystemBlobStore(store / "blobs")
    assert {k: blobs.get(k) for k in items} == items  # plaintext restored exactly


# --- rotate ------------------------------------------------------------------


def test_rotate_swaps_token_without_re_encrypting_blobs(tmp_path):
    store = tmp_path / "store"
    _seed(store, {"k": b"secret"})
    old, new = _token(), _token()
    enc = _encryptor(store)
    enc.enable(old)
    raw_before = _raw(store, "k")
    enc.rotate(old, new)

    assert _raw(store, "k") == raw_before  # blob bytes unchanged (data key unchanged)
    assert _read_decrypted(store, new, "k") == b"secret"  # new token reads
    with pytest.raises(WrongEncryptionToken):
        build_use_cases(_db_factory(store), store, encryption_token=old)  # old token rejected


# --- invalidate --------------------------------------------------------------


def test_invalidate_wipes_to_empty_public_store(tmp_path):
    store = tmp_path / "store"
    _seed(store, {"k": b"x"})
    enc = _encryptor(store)
    enc.enable(_token())
    (store / "executions.sqlite3").write_bytes(b"db")  # stand-in for the records

    enc.invalidate()

    assert _state(store) is EncryptionState.PUBLIC
    assert not (store / "blobs").exists()
    assert not (store / "executions.sqlite3").exists()


# --- wrong token / wrong state ----------------------------------------------


def test_disable_with_wrong_token_is_rejected(tmp_path):
    store = tmp_path / "store"
    _seed(store, {"k": b"x"})
    enc = _encryptor(store)
    enc.enable(_token())
    with pytest.raises(WrongEncryptionToken):
        enc.disable(_token())


def test_enable_on_already_encrypted_raises(tmp_path):
    store = tmp_path / "store"
    _seed(store, {"k": b"x"})
    token = _token()
    enc = _encryptor(store)
    enc.enable(token)
    with pytest.raises(EncryptionStateError):
        enc.enable(token)


def test_disable_on_public_store_raises(tmp_path):
    store = tmp_path / "store"
    _seed(store, {"k": b"x"})
    with pytest.raises(EncryptionStateError):
        _encryptor(store).disable(_token())


# --- crash recovery ----------------------------------------------------------


def test_recover_rolls_forward_an_interrupted_commit(tmp_path, monkeypatch):
    store = tmp_path / "store"
    _seed(store, {"k": b"PLAINMARKER"})
    token = _token()

    # interrupt enable right after the marker is written, before the commit finishes
    monkeypatch.setattr(StoreEncryptor, "_finish_commit", lambda self, marker: None)
    _encryptor(store).enable(token)
    monkeypatch.undo()

    # mid-migration: marker + staging present, manifest not yet written, blobs untouched
    assert (store / _MARKER).exists()
    assert _state(store) is EncryptionState.PUBLIC

    # opening the store recovers -> rolls forward to encrypted, content intact
    assert _read_decrypted(store, token, "k") == b"PLAINMARKER"
    assert _state(store) is EncryptionState.ENCRYPTED
    assert not (store / _MARKER).exists()


def test_recover_rolls_back_orphan_staging(tmp_path):
    store = tmp_path / "store"
    _seed(store, {"k": b"plain"})
    # staging present but NO marker == crashed before the commit point
    (store / "blobs.staging").mkdir()
    (store / "blobs.staging" / "k").write_bytes(b"half-encrypted")

    _encryptor(store).recover()

    assert not (store / "blobs.staging").exists()  # rolled back
    assert FilesystemBlobStore(store / "blobs").get("k") == b"plain"  # untouched
    assert _state(store) is EncryptionState.PUBLIC


def test_recover_is_a_noop_when_clean(tmp_path):
    store = tmp_path / "store"
    _seed(store, {"k": b"x"})
    _encryptor(store).recover()  # nothing pending
    assert FilesystemBlobStore(store / "blobs").get("k") == b"x"
    assert _state(store) is EncryptionState.PUBLIC
