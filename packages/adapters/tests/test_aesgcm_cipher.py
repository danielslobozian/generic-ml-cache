# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for AesGcmCipher (the encryption envelope)."""

from __future__ import annotations

import pytest

pytest.importorskip("cryptography")  # the optional [encryption] extra

from generic_ml_cache_adapters.adapter.out.crypto.aesgcm_cipher import AesGcmCipher  # noqa: E402
from generic_ml_cache_core.common.errors import WrongEncryptionToken  # noqa: E402


def _cipher() -> AesGcmCipher:
    return AesGcmCipher()


# --- token generation --------------------------------------------------------


def test_generated_tokens_are_unique_and_substantial():
    cipher = _cipher()
    tokens = {cipher.generate_token() for _ in range(100)}
    assert len(tokens) == 100  # no collisions
    assert all(len(t) >= 32 for t in tokens)  # high-entropy, url-safe


# --- envelope round-trip -----------------------------------------------------


def test_create_then_open_recovers_the_same_data_key():
    cipher = _cipher()
    token = cipher.generate_token()
    manifest, data_key = cipher.create_envelope(token)
    assert len(data_key) == 32  # AES-256
    assert cipher.open_envelope(token, manifest) == data_key


def test_open_is_deterministic_across_calls():
    cipher = _cipher()
    token = cipher.generate_token()
    manifest, _ = cipher.create_envelope(token)
    # re-derivation from token + stored salt is deterministic
    assert cipher.open_envelope(token, manifest) == cipher.open_envelope(token, manifest)


def test_each_envelope_uses_a_fresh_salt():
    cipher = _cipher()
    token = cipher.generate_token()
    m1, _ = cipher.create_envelope(token)
    m2, _ = cipher.create_envelope(token)
    assert m1.kdf_salt != m2.kdf_salt
    assert m1.wrapped_data_key != m2.wrapped_data_key


# --- content encryption ------------------------------------------------------


def test_encrypt_then_decrypt_round_trips():
    cipher = _cipher()
    _, data_key = cipher.create_envelope(cipher.generate_token())
    plaintext = b"the model's answer \xf0\x9f\x9a\x80 with bytes"
    ciphertext = cipher.encrypt(data_key, plaintext)
    assert ciphertext != plaintext
    assert cipher.decrypt(data_key, ciphertext) == plaintext


def test_each_encryption_is_nondeterministic_but_decrypts():
    cipher = _cipher()
    _, data_key = cipher.create_envelope(cipher.generate_token())
    a = cipher.encrypt(data_key, b"same input")
    b = cipher.encrypt(data_key, b"same input")
    assert a != b  # fresh nonce each time
    assert cipher.decrypt(data_key, a) == cipher.decrypt(data_key, b) == b"same input"


# --- wrong token / tampering -------------------------------------------------


def test_wrong_token_cannot_open_the_envelope():
    cipher = _cipher()
    manifest, _ = cipher.create_envelope(cipher.generate_token())
    with pytest.raises(WrongEncryptionToken):
        cipher.open_envelope(cipher.generate_token(), manifest)


def test_tampered_wrapped_key_is_rejected():
    cipher = _cipher()
    token = cipher.generate_token()
    manifest, _ = cipher.create_envelope(token)
    tampered = bytearray(manifest.wrapped_data_key)
    tampered[-1] ^= 0x01
    from dataclasses import replace

    with pytest.raises(WrongEncryptionToken):
        cipher.open_envelope(token, replace(manifest, wrapped_data_key=bytes(tampered)))


def test_tampered_ciphertext_is_rejected():
    cipher = _cipher()
    _, data_key = cipher.create_envelope(cipher.generate_token())
    blob = bytearray(cipher.encrypt(data_key, b"answer"))
    blob[-1] ^= 0x01
    with pytest.raises(WrongEncryptionToken):
        cipher.decrypt(data_key, bytes(blob))


# --- rotation ----------------------------------------------------------------


def test_rotation_rewraps_the_same_data_key_under_a_new_token():
    cipher = _cipher()
    old_token = cipher.generate_token()
    manifest, data_key = cipher.create_envelope(old_token)

    new_token = cipher.generate_token()
    rotated = cipher.rewrap(data_key, new_token)

    # the new token opens it to the SAME data key (content never re-encrypted) ...
    assert cipher.open_envelope(new_token, rotated) == data_key
    # ... and the old token no longer works on the rotated manifest.
    with pytest.raises(WrongEncryptionToken):
        cipher.open_envelope(old_token, rotated)


def test_data_encrypted_before_rotation_still_decrypts_after():
    cipher = _cipher()
    old_token = cipher.generate_token()
    _, data_key = cipher.create_envelope(old_token)
    ciphertext = cipher.encrypt(data_key, b"recorded answer")

    new_token = cipher.generate_token()
    rotated = cipher.rewrap(data_key, new_token)

    # after rotation you open with the NEW token to recover the (same) data key ...
    recovered = cipher.open_envelope(new_token, rotated)
    assert recovered == data_key
    # ... and content encrypted before the rotation still decrypts.
    assert cipher.decrypt(recovered, ciphertext) == b"recorded answer"
