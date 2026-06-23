# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EncryptionState."""

from __future__ import annotations

from enum import Enum


class EncryptionState(Enum):
    """Whether a store is encrypted — a single, store-wide, all-or-nothing state.

    There is no per-entry or per-namespace encryption (that was the multi-user
    "scope" idea, deliberately removed): the whole local store is either ``PUBLIC``
    (plaintext) or ``ENCRYPTED`` (everything persisted is encrypted under one
    token). The state is *derived*, not a flag — a store is ``ENCRYPTED`` exactly
    when its encryption manifest is present.
    """

    PUBLIC = "public"
    ENCRYPTED = "encrypted"
