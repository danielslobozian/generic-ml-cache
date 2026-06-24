# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ApiCallIdentity."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)


def _identity(**overrides) -> ApiCallIdentity:
    defaults = dict(provider="openai", model="gpt-x", messages_fingerprint="fp", effort="")
    defaults.update(overrides)
    return ApiCallIdentity(**defaults)


def test_is_a_call_identity():
    assert isinstance(_identity(), CallIdentity)


def test_key_is_hex_and_deterministic():
    key = _identity().generate_key()
    assert len(key) == 64
    assert key == _identity().generate_key()


def test_different_providers_differ():
    assert (
        _identity(provider="openai").generate_key()
        != _identity(provider="anthropic").generate_key()
    )


def test_different_models_differ():
    assert _identity(model="gpt-x").generate_key() != _identity(model="gpt-y").generate_key()


def test_different_messages_differ():
    assert (
        _identity(messages_fingerprint="a").generate_key()
        != _identity(messages_fingerprint="b").generate_key()
    )


def test_different_efforts_differ():
    assert _identity(effort="low").generate_key() != _identity(effort="high").generate_key()


def test_empty_effort_and_absent_effort_are_equal():
    assert _identity(effort="").generate_key() == ApiCallIdentity(
        provider="openai", model="gpt-x", messages_fingerprint="fp"
    ).generate_key()


def test_never_collides_with_a_passthrough_key():
    api_key = _identity(provider="claude", messages_fingerprint="x").generate_key()
    passthrough_key = PassthroughCallIdentity(
        client="claude", native_args_fingerprint="x"
    ).generate_key()
    assert api_key != passthrough_key
