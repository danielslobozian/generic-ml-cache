# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CipherPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Tuple

from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)


class CipherPort(ABC):
    """Outbound port for at-rest encryption — the envelope, never the policy.

    It owns only the cryptography: generate a token, build/open the key envelope,
    and encrypt/decrypt bytes under the (in-memory) data key. It never stores
    anything, never decides *what* is encrypted, and never touches the store —
    those are the use case's job. Swappable like any adapter.

    The model is envelope encryption: content is encrypted under a random **data
    key**; the data key is stored **wrapped** under a key derived from the token +
    a salt (both kept in the :class:`EncryptionManifest`). The token and the
    derived keys are never persisted.
    """

    @abstractmethod
    def generate_token(self) -> str:
        """Return a fresh, high-entropy token for the user to keep. gmlcache never
        accepts an outside password; tokens are generated here and shown once."""

    @abstractmethod
    def create_envelope(self, token: str) -> Tuple[EncryptionManifest, bytes]:
        """Start a new encrypted store under ``token``: generate a random data key,
        wrap it under a key derived from ``token`` + a fresh salt, and return the
        ``(manifest, data_key)``. The data key is returned for immediate use; only
        the manifest is meant to be stored."""

    @abstractmethod
    def open_envelope(self, token: str, manifest: EncryptionManifest) -> bytes:
        """Re-derive and return the data key from ``token`` + ``manifest``. Raises
        :class:`WrongEncryptionToken` if the token is wrong or the wrapped key was
        tampered with."""

    @abstractmethod
    def rewrap(self, data_key: bytes, new_token: str) -> EncryptionManifest:
        """Rotation: wrap an already-opened ``data_key`` under ``new_token`` (with a
        fresh salt) and return the new manifest. The content is **not** re-encrypted
        — only the small wrapped-key envelope changes."""

    @abstractmethod
    def encrypt(self, data_key: bytes, plaintext: bytes) -> bytes:
        """Authenticated-encrypt ``plaintext`` under ``data_key``."""

    @abstractmethod
    def decrypt(self, data_key: bytes, ciphertext: bytes) -> bytes:
        """Reverse :meth:`encrypt`. Raises :class:`WrongEncryptionToken` if the
        ciphertext fails its integrity check (wrong key or tampering)."""
