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

from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.cipher_port import CipherPort
from generic_ml_cache_core.common.errors import EncryptionTokenRequired


class EncryptingBlobStore(BlobStorePort):
    """Wrap a blob store so its bytes are encrypted at rest under ``data_key``."""

    def __init__(self, inner: BlobStorePort, cipher: CipherPort, data_key: bytes) -> None:
        self._inner = inner
        self._cipher = cipher
        self._data_key = data_key

    def get(self, key: str) -> bytes | None:
        blob = self._inner.get(key)
        if blob is None:
            return None
        return self._cipher.decrypt(self._data_key, blob)

    def put(self, key: str, output: bytes) -> None:
        self._inner.put(key, self._cipher.encrypt(self._data_key, output))

    def remove(self, key: str) -> None:
        self._inner.remove(key)


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

    def remove(self, key: str) -> None:
        self._inner.remove(key)
