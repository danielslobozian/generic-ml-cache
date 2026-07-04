# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EncryptingBlobStore: transparent at-rest encryption over any blob store.

A decorator that encrypts content on ``put`` and decrypts on ``get``, keyed by the
in-memory data key. The blob **key stays the plaintext content fingerprint**, so
content-addressing, dedup, and the execution record are untouched — encryption is a
storage layer *beneath* the key, never part of it. (Encryption is non-deterministic,
so the same plaintext stores different ciphertext each time; the key is the plaintext
hash, so dedup still works.)

Pure: it depends only on the ports (a ``BlobStorePort`` to wrap and a ``CipherPort``
to call), never on the crypto library directly.
"""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.cipher_port import CipherPort
from generic_ml_cache_core.common.errors import (
    EncryptionTokenRequired,
    StoreCorrupt,
    WrongEncryptionToken,
)


class EncryptingBlobStore(BlobStorePort):
    """Wrap a blob store so its bytes are encrypted at rest under ``data_key``."""

    def __init__(self, inner: BlobStorePort, cipher: CipherPort, data_key: bytes) -> None:
        self._inner = inner
        self._cipher = cipher
        self._data_key = data_key

    def get(self, key: str) -> bytes | None:
        blob = self._inner.get(BlobKey(key))
        if blob is None:
            return None
        try:
            return self._cipher.decrypt(self._data_key, blob)
        except WrongEncryptionToken as exc:
            # The data key already opened the envelope (the token was verified at
            # wiring), so a CONTENT decrypt failure means the stored blob is corrupt
            # or tampered — not a token problem. Surface it as corruption so the
            # serve path self-heals by re-running (S5c → S4), never mislabels it a
            # wrong token.
            raise StoreCorrupt(f"blob {key} failed to decrypt with a valid token") from exc

    def put(self, key: str, output: bytes) -> None:
        self._inner.put(BlobKey(key), self._cipher.encrypt(self._data_key, output))

    def exists(self, key: str) -> bool:
        # Presence is about the ciphertext file, not its plaintext — no decryption.
        return self._inner.exists(BlobKey(key))

    def is_healthy(self) -> bool:
        # Liveness is about the underlying store, not the cipher.
        return self._inner.is_healthy()

    def remove(self, key: str) -> None:
        self._inner.remove(BlobKey(key))


class TokenRequiredBlobStore(BlobStorePort):
    """Stand-in used when the store is encrypted but no token was supplied.

    Reading or writing content needs the token, so ``get``/``put`` fail with a clear
    :class:`EncryptionTokenRequired`. Removal is keyless (it deletes ciphertext bytes
    without reading them), so it passes through — letting metadata-only commands and
    cleanup work without the token, while content operations are blocked.
    """

    def __init__(self, inner: BlobStorePort) -> None:
        self._inner = inner

    def get(self, key: str) -> bytes | None:
        raise EncryptionTokenRequired("the store is encrypted — provide the token to read it")

    def put(self, key: str, output: bytes) -> None:
        raise EncryptionTokenRequired("the store is encrypted — provide the token to record")

    def ensure_available_for_content(self) -> None:
        # The up-front token gate (S5a): a content op fails HERE, before the client
        # call, instead of lazily on the first get/put after a wasted run.
        raise EncryptionTokenRequired(
            "the store is encrypted — provide the token to run a content operation"
        )

    def exists(self, key: str) -> bool:
        # A presence test reads no content, so it works without the token (like remove).
        return self._inner.exists(BlobKey(key))

    def is_healthy(self) -> bool:
        # A liveness probe writes no user content, so it needs no token either.
        return self._inner.is_healthy()

    def remove(self, key: str) -> None:
        self._inner.remove(BlobKey(key))
