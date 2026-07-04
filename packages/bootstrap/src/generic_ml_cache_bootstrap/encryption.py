# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Driver-facing facade for the store-encryption commands (W28).

The CLI's ``gmlcache encrypt / decrypt / rotate / invalidate / status`` commands
are driver *feature* logic, but running them means constructing concrete crypto
adapters (the cipher, the manifest store, the store lock, the store encryptor) —
the ``cli._compose -> adapters.…crypto/persistence`` edges W28 removes. This facade
owns that wiring in the composition root; the CLI controller keeps only its own
user-facing concerns (prompts, exit codes, the pip-install hint).

The operations raise the same core errors they always did
(``EncryptionStateError`` / ``WrongEncryptionToken`` / ``StoreLocked``) for the
driver to translate, plus a bare ``ImportError`` when the optional ``[encryption]``
extra is not installed (only the token-minting operations need the cipher).
"""

from __future__ import annotations

from pathlib import Path

from generic_ml_cache_adapters.adapter.outbound.crypto.filesystem_encryption_manifest_store import (
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_adapters.adapter.outbound.crypto.store_encryptor import StoreEncryptor
from generic_ml_cache_adapters.adapter.outbound.persistence.filesystem_store_lock import (
    FilesystemStoreLock,
)
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)
from generic_ml_cache_core.application.port.outbound.cipher_port import CipherPort


def _load_cipher() -> CipherPort:
    """Construct the AES-GCM cipher. Raises ``ImportError`` if the optional
    ``[encryption]`` extra (the ``cryptography`` dependency) is not installed."""
    from generic_ml_cache_adapters.adapter.outbound.crypto.aesgcm_cipher import AesGcmCipher

    return AesGcmCipher()


class StoreEncryptionOps:
    """Composition-root facade for the store-encryption operations, so a driver can
    run the encrypt commands without importing any concrete crypto adapter."""

    def __init__(self, store_root: Path) -> None:
        self._store_root = Path(store_root)

    def status(self) -> EncryptionState:
        """The store's current encryption state (no cipher needed)."""
        return FilesystemEncryptionManifestStore(self._store_root).state()

    def enable(self) -> str:
        """Enable encryption and return the freshly minted token (shown once)."""
        cipher = _load_cipher()
        token = cipher.generate_token()
        self._encryptor(cipher).enable(token)
        return token

    def disable(self, token: str) -> None:
        """Decrypt the store back to plaintext with the current token."""
        self._encryptor(_load_cipher()).disable(token)

    def rotate(self, old_token: str) -> str:
        """Rotate to a freshly minted token and return it (shown once)."""
        cipher = _load_cipher()
        new_token = cipher.generate_token()
        self._encryptor(cipher).rotate(old_token, new_token)
        return new_token

    def invalidate(self) -> None:
        """Crypto-shred: wipe the cache and return the store to empty + public."""
        self._encryptor().invalidate()

    def _encryptor(self, cipher: CipherPort | None = None) -> StoreEncryptor:
        return StoreEncryptor(
            self._store_root,
            FilesystemEncryptionManifestStore(self._store_root),
            FilesystemStoreLock(self._store_root),
            cipher,
        )
