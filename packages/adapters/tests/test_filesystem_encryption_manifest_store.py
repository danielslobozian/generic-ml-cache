# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FilesystemEncryptionManifestStore."""

from __future__ import annotations

from generic_ml_cache_adapters.adapter.out.crypto.filesystem_encryption_manifest_store import (
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)


def _manifest() -> EncryptionManifest:
    # arbitrary non-secret bytes, including a high byte to exercise base64
    return EncryptionManifest(kdf_salt=b"\x00\x01salt", wrapped_data_key=b"wrapped\xff", version=1)


def test_absent_manifest_means_public(tmp_path):
    store = FilesystemEncryptionManifestStore(tmp_path)
    assert store.load() is None
    assert store.state() is EncryptionState.PUBLIC


def test_save_then_load_round_trips_and_is_encrypted(tmp_path):
    store = FilesystemEncryptionManifestStore(tmp_path)
    manifest = _manifest()
    store.save(manifest)
    assert store.load() == manifest  # bytes survive base64 round-trip
    assert store.state() is EncryptionState.ENCRYPTED


def test_delete_returns_to_public(tmp_path):
    store = FilesystemEncryptionManifestStore(tmp_path)
    store.save(_manifest())
    store.delete()
    assert store.load() is None
    assert store.state() is EncryptionState.PUBLIC


def test_delete_is_a_no_op_when_absent(tmp_path):
    FilesystemEncryptionManifestStore(tmp_path).delete()  # must not raise


def test_save_leaves_no_temp_file_behind(tmp_path):
    FilesystemEncryptionManifestStore(tmp_path).save(_manifest())
    assert [p.name for p in tmp_path.iterdir()] == ["encryption.json"]
