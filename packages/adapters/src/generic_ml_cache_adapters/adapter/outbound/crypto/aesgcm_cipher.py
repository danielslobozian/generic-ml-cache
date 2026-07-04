# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AesGcmCipher: the CipherPort over a vetted AEAD + HKDF.

Uses the ``cryptography`` library (optional ``[encryption]`` extra) — AES-256-GCM
for authenticated encryption and HKDF-SHA256 for key derivation. The token is
gmlcache-generated and high-entropy, so HKDF (built for high-entropy keying
material) is the right KDF; we never accept a low-entropy human passphrase, so no
password-hardening KDF (Argon2id) is needed.

**Content encryption derives a fresh per-write subkey (X23).** A "cache forever"
store can accumulate millions of blobs, and a bare random 96-bit GCM nonce under one
long-lived key has a NIST SP 800-38D collision bound around 2^32 encryptions. So each
content ``encrypt`` HKDFs a *unique* AES key from the data key + a random 256-bit
salt (stored ahead of the nonce): every blob is sealed under its own key, so no single
key ever nears the random-nonce bound — with **no 2^32 ceiling and no persistent
counter to trust** (a counter that resets/rolls back would be a catastrophic
nonce-reuse hazard). The rare key-*wrap* path (one per token) keeps the plain seal.
"""

from __future__ import annotations

import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)
from generic_ml_cache_core.application.port.outbound.cipher_port import CipherPort
from generic_ml_cache_core.common.errors import WrongEncryptionToken

_KEY_BYTES = 32  # AES-256
_NONCE_BYTES = 12  # GCM standard nonce
_SALT_BYTES = 16
#: Per-write content-subkey salt (X23): 256 bits, so the birthday bound on a repeated
#: salt (~2^128 writes) is astronomically beyond any real store — no 2^32 ceiling.
_CONTENT_SUBKEY_SALT_BYTES = 32
_TOKEN_BYTES = 32  # 256-bit token
# Owned, scanner-friendly provenance prefix (GitHub-style ``<prefix>_<secret>``): it
# lets our own log scrubber and external secret scanners recognise a leaked token by
# shape, which the bare 64-hex form (indistinguishable from a SHA-256 key) could not.
# The prefix is presentation only — it is stripped before key derivation, so a
# ``gmlc_<hex>`` token and the legacy bare ``<hex>`` derive the *same* key (a store
# encrypted before this change still opens, with either form).
_TOKEN_PREFIX = "gmlc_"

# Domain-separated HKDF label: the wrapping key has one role only (wrap the data
# key). The data key is random, never derived from the token, so nothing the store
# keeps can relate back to the token.
_KEK_INFO = b"generic-ml-cache/kek/v1"
# Associated data binds each AEAD operation to its purpose, so a wrapped-key blob
# and a content blob can never be swapped for one another.
_WRAP_AAD = b"generic-ml-cache/wrapped-data-key/v1"
_CONTENT_AAD = b"generic-ml-cache/content/v1"
# Domain-separated HKDF label for the per-write content subkey (X23), distinct from
# the KEK label so a content subkey and a wrapping key can never coincide.
_CONTENT_SUBKEY_INFO = b"generic-ml-cache/content-subkey/v1"


class AesGcmCipher(CipherPort):
    """AES-256-GCM + HKDF-SHA256 implementation of the encryption envelope."""

    def generate_token(self) -> str:
        # Hex (not url-safe base64): the token body never starts with "-", so it is safe
        # to pass as a CLI argument value (argparse would read a leading "-" as a flag)
        # and carries no shell-special characters. The ``gmlc_`` prefix keeps that
        # property (letters + underscore) while making the token scanner-recognisable.
        return _TOKEN_PREFIX + secrets.token_hex(_TOKEN_BYTES)

    def create_envelope(self, token: str) -> tuple[EncryptionManifest, bytes]:
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
        # Per-write subkey (X23): a fresh random salt derives a unique AES key for this
        # blob, so its GCM nonce is the only one ever used under that key — the random-
        # nonce 2^32 bound never applies. Blob = salt || nonce || ciphertext+tag.
        salt = secrets.token_bytes(_CONTENT_SUBKEY_SALT_BYTES)
        subkey = self._content_subkey(data_key, salt)
        return salt + self._aead_seal(subkey, plaintext, _CONTENT_AAD)

    def decrypt(self, data_key: bytes, ciphertext: bytes) -> bytes:
        salt, sealed = (
            ciphertext[:_CONTENT_SUBKEY_SALT_BYTES],
            ciphertext[_CONTENT_SUBKEY_SALT_BYTES:],
        )
        subkey = self._content_subkey(data_key, salt)
        return self._aead_open(subkey, sealed, _CONTENT_AAD)

    # -- internals --------------------------------------------------------

    def _wrap(self, data_key: bytes, token: str, salt: bytes) -> bytes:
        kek = self._derive_kek(token, salt)
        return self._aead_seal(kek, data_key, _WRAP_AAD)

    @staticmethod
    def _derive_kek(token: str, salt: bytes) -> bytes:
        # Strip the optional provenance prefix so the derived key depends only on the
        # secret body: a ``gmlc_<hex>`` token and the legacy bare ``<hex>`` key alike
        # (back-compat). A legacy bare token is all hex digits, so it can never *start
        # with* the literal ``gmlc_`` (whose letters/underscore are not hex) — thus
        # ``removeprefix`` only ever strips a real prefix, never mangling an old token.
        seed = token.removeprefix(_TOKEN_PREFIX)
        hkdf = HKDF(algorithm=SHA256(), length=_KEY_BYTES, salt=salt, info=_KEK_INFO)
        return hkdf.derive(seed.encode("utf-8"))

    @staticmethod
    def _content_subkey(data_key: bytes, salt: bytes) -> bytes:
        # HKDF a per-write AES key from the (high-entropy) data key + this write's
        # random salt (X23). No token, no counter — just fresh keying material per blob.
        hkdf = HKDF(algorithm=SHA256(), length=_KEY_BYTES, salt=salt, info=_CONTENT_SUBKEY_INFO)
        return hkdf.derive(data_key)

    @staticmethod
    def _aead_seal(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        return nonce + AESGCM(key).encrypt(nonce, plaintext, aad)

    @staticmethod
    def _aead_open(key: bytes, blob: bytes, aad: bytes) -> bytes:
        nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, aad)
        except (InvalidTag, ValueError) as exc:
            # InvalidTag = wrong key / tampered bytes; ValueError = a malformed or
            # truncated blob (e.g. too short to hold a full nonce). Both mean the
            # stored blob cannot be trusted — never a raw crash across the boundary.
            raise WrongEncryptionToken("decryption failed: wrong token or tampered data") from exc
