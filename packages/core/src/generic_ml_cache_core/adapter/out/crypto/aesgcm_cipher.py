# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AesGcmCipher: the CipherPort over a vetted AEAD + HKDF.

Uses the ``cryptography`` library (optional ``[encryption]`` extra) — AES-256-GCM
for authenticated encryption and HKDF-SHA256 for key derivation. The token is
gmlcache-generated and high-entropy, so HKDF (built for high-entropy keying
material) is the right KDF; we never accept a low-entropy human passphrase, so no
password-hardening KDF (Argon2id) is needed.
"""

from __future__ import annotations

import secrets
from typing import Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)
from generic_ml_cache_core.application.port.out.cipher_port import CipherPort
from generic_ml_cache_core.common.errors import WrongEncryptionToken

_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # GCM standard nonce
_SALT_BYTES = 16
_TOKEN_BYTES = 32  # 256-bit token

# Domain-separated HKDF label: the wrapping key has one role only (wrap the data
# key). The data key is random, never derived from the token, so nothing the store
# keeps can relate back to the token.
_KEK_INFO = b"generic-ml-cache/kek/v1"
# Associated data binds each AEAD operation to its purpose, so a wrapped-key blob
# and a content blob can never be swapped for one another.
_WRAP_AAD = b"generic-ml-cache/wrapped-data-key/v1"
_CONTENT_AAD = b"generic-ml-cache/content/v1"


class AesGcmCipher(CipherPort):
    """AES-256-GCM + HKDF-SHA256 implementation of the encryption envelope."""

    def generate_token(self) -> str:
        return secrets.token_urlsafe(_TOKEN_BYTES)

    def create_envelope(self, token: str) -> Tuple[EncryptionManifest, bytes]:
        data_key = AESGCM.generate_key(bit_length=_KEY_BYTES * 8)
        salt = secrets.token_bytes(_SALT_BYTES)
        wrapped = self._wrap(data_key, token, salt)
        return EncryptionManifest(kdf_salt=salt, wrapped_data_key=wrapped), data_key

    def open_envelope(self, token: str, manifest: EncryptionManifest) -> bytes:
        kek = self._derive_kek(token, manifest.kdf_salt)
        return self._aead_open(kek, manifest.wrapped_data_key, _WRAP_AAD)

    def rewrap(self, data_key: bytes, new_token: str) -> EncryptionManifest:
        salt = secrets.token_bytes(_SALT_BYTES)
        wrapped = self._wrap(data_key, new_token, salt)
        return EncryptionManifest(kdf_salt=salt, wrapped_data_key=wrapped)

    def encrypt(self, data_key: bytes, plaintext: bytes) -> bytes:
        return self._aead_seal(data_key, plaintext, _CONTENT_AAD)

    def decrypt(self, data_key: bytes, ciphertext: bytes) -> bytes:
        return self._aead_open(data_key, ciphertext, _CONTENT_AAD)

    # -- internals --------------------------------------------------------

    def _wrap(self, data_key: bytes, token: str, salt: bytes) -> bytes:
        kek = self._derive_kek(token, salt)
        return self._aead_seal(kek, data_key, _WRAP_AAD)

    @staticmethod
    def _derive_kek(token: str, salt: bytes) -> bytes:
        hkdf = HKDF(algorithm=SHA256(), length=_KEY_BYTES, salt=salt, info=_KEK_INFO)
        return hkdf.derive(token.encode("utf-8"))

    @staticmethod
    def _aead_seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)

    @staticmethod
    def _aead_open(key: bytes, blob: bytes, aad: bytes) -> bytes:
        nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, aad)
        except InvalidTag as exc:
            raise WrongEncryptionToken("decryption failed: wrong token or tampered data") from exc
