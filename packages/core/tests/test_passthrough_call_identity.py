# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for PassthroughCallIdentity."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)


def test_is_a_call_identity():
    assert isinstance(
        PassthroughCallIdentity(client="claude", native_args_fingerprint="fp"), CallIdentity
    )


def test_generate_key_is_hex_and_deterministic():
    identity = PassthroughCallIdentity(client="claude", native_args_fingerprint="fp")
    key = identity.generate_key()
    assert len(key) == 64
    assert key == identity.generate_key()


def test_different_clients_produce_different_keys():
    first = PassthroughCallIdentity(client="claude", native_args_fingerprint="fp").generate_key()
    second = PassthroughCallIdentity(client="codex", native_args_fingerprint="fp").generate_key()
    assert first != second


def test_different_args_produce_different_keys():
    first = PassthroughCallIdentity(client="claude", native_args_fingerprint="a").generate_key()
    second = PassthroughCallIdentity(client="claude", native_args_fingerprint="b").generate_key()
    assert first != second


def test_never_collides_with_a_managed_key():
    """The kind is folded into the key, so even identical-looking fields across
    kinds yield different keys — a passthrough lookup can never hit a managed
    execution in the shared repository."""
    passthrough = PassthroughCallIdentity(
        client="claude", native_args_fingerprint="x"
    ).generate_key()
    managed = ManagedCallIdentity(
        client="claude",
        model="",
        effort="",
        context_fingerprint="",
        prompt_fingerprint="",
        client_args_fingerprint="x",
    ).generate_key()
    assert passthrough != managed
