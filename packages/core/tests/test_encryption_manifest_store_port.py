# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Optional

from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)
from generic_ml_cache_core.application.port.out.encryption_manifest_store_port import (
    EncryptionManifestStorePort,
)


class _StubManifestStore(EncryptionManifestStorePort):
    def __init__(self, manifest: Optional[EncryptionManifest]) -> None:
        self._manifest = manifest

    def load(self) -> Optional[EncryptionManifest]:
        return self._manifest

    def save(self, manifest: EncryptionManifest) -> None:
        pass

    def delete(self) -> None:
        pass


class TestEncryptionManifestStorePortState:
    def test_no_manifest_returns_public(self):
        store = _StubManifestStore(manifest=None)
        assert store.state() == EncryptionState.PUBLIC

    def test_manifest_present_returns_encrypted(self):
        manifest = EncryptionManifest(kdf_salt=b"s", wrapped_data_key=b"k")
        store = _StubManifestStore(manifest=manifest)
        assert store.state() == EncryptionState.ENCRYPTED

    def test_state_calls_load_each_time(self):
        store = _StubManifestStore(manifest=None)
        assert store.state() == EncryptionState.PUBLIC
        assert store.state() == EncryptionState.PUBLIC

    def test_state_reflects_load_returning_manifest(self):
        manifest = EncryptionManifest(kdf_salt=b"salt123", wrapped_data_key=b"wrappedkey")
        store = _StubManifestStore(manifest=manifest)
        result = store.state()
        assert result is EncryptionState.ENCRYPTED
