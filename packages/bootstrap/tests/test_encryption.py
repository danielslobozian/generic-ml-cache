# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The driver-facing store-encryption facade (W28).

Lets the CLI's encrypt/decrypt/rotate/invalidate/status commands run without
importing any concrete crypto adapter. Needs the optional ``[encryption]`` extra.
"""

from pathlib import Path

import pytest

pytest.importorskip("cryptography")

from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (  # noqa: E402
    EncryptionState,
)
from generic_ml_cache_core.common.errors import WrongEncryptionToken  # noqa: E402

from generic_ml_cache_bootstrap.encryption import StoreEncryptionOps  # noqa: E402


def test_status_starts_public(tmp_path: Path):
    assert StoreEncryptionOps(tmp_path).status() is EncryptionState.PUBLIC


def test_enable_mints_a_token_and_flips_to_encrypted(tmp_path: Path):
    ops = StoreEncryptionOps(tmp_path)
    token = ops.enable()
    assert token
    assert ops.status() is EncryptionState.ENCRYPTED


def test_disable_returns_the_store_to_public(tmp_path: Path):
    ops = StoreEncryptionOps(tmp_path)
    token = ops.enable()
    ops.disable(token)
    assert ops.status() is EncryptionState.PUBLIC


def test_disable_with_the_wrong_token_is_rejected(tmp_path: Path):
    ops = StoreEncryptionOps(tmp_path)
    ops.enable()
    with pytest.raises(WrongEncryptionToken):
        ops.disable("definitely-not-the-right-token-xyz")


def test_rotate_swaps_to_a_new_token(tmp_path: Path):
    ops = StoreEncryptionOps(tmp_path)
    old = ops.enable()
    new = ops.rotate(old)
    assert new != old
    assert ops.status() is EncryptionState.ENCRYPTED
    with pytest.raises(WrongEncryptionToken):
        ops.disable(old)
    ops.disable(new)
    assert ops.status() is EncryptionState.PUBLIC


def test_invalidate_wipes_back_to_public_without_a_token(tmp_path: Path):
    ops = StoreEncryptionOps(tmp_path)
    ops.enable()
    ops.invalidate()
    assert ops.status() is EncryptionState.PUBLIC
