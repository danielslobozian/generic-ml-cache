# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EncryptionManifest."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EncryptionManifest:
    """The non-secret material a store keeps so a token can re-derive the key.

    Envelope encryption (see the data-handling design note): the content is
    encrypted under a random **data key**; that data key is itself stored
    **wrapped** (authenticated-encrypted) under a key derived from the user's
    token + ``kdf_salt``. None of this is secret on its own:

    - ``kdf_salt`` — random, non-secret; makes the key derivation unique per store.
    - ``wrapped_data_key`` — the data key encrypted under the token-derived key;
      useless without the token.

    The **token itself and the derived keys are never stored** — the token is
    supplied at runtime and the keys live only in memory during a call. Rotation
    re-wraps the *same* data key under a new token (so the content is never
    re-encrypted); invalidation deletes the wrapped key (crypto-shred).
    """

    kdf_salt: bytes
    wrapped_data_key: bytes
    version: int = 1
