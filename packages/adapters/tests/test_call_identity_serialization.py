# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the call-identity serializer (round-trips every kind)."""

from __future__ import annotations

import pytest
from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.api_passthrough_call_identity import (
    ApiPassthroughCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)

from generic_ml_cache_adapters.adapter.outbound.persistence.call_identity_serialization import (
    SerializedIdentity,
    deserialize_identity,
    serialize_identity,
)


def _round_trip(identity):
    return deserialize_identity(serialize_identity(identity))


def test_managed_round_trip_preserves_all_fields_and_key():
    identity = ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="ctx",
        prompt_fingerprint="prompt",
        input_file_fingerprints={"/src/a.py": "sha_a", "/src/b.py": "sha_b"},
        client_args_fingerprint="args",
        grants=frozenset({"net", "read"}),
    )
    restored = _round_trip(identity)
    assert restored == identity
    assert restored.generate_key() == identity.generate_key()


def test_managed_denormalized_columns():
    serialized = serialize_identity(
        ManagedCallIdentity(
            client="claude",
            model="sonnet",
            effort="high",
            context_fingerprint="c",
            prompt_fingerprint="p",
        )
    )
    assert serialized.kind == "local_managed"
    assert (serialized.client, serialized.model, serialized.effort) == ("claude", "sonnet", "high")


def test_passthrough_round_trip():
    identity = PassthroughCallIdentity(client="codex", native_args_fingerprint="fp")
    restored = _round_trip(identity)
    assert restored == identity
    assert restored.generate_key() == identity.generate_key()


def test_passthrough_denormalized_columns():
    serialized = serialize_identity(
        PassthroughCallIdentity(client="codex", native_args_fingerprint="fp")
    )
    assert serialized.kind == "local_passthrough"
    assert serialized.client == "codex"
    assert serialized.model == ""


def test_api_round_trip():
    identity = ApiCallIdentity(
        provider="openai",
        model="gpt-x",
        context_fingerprint="cf",
        prompt_fingerprint="pf",
        effort="high",
    )
    restored = _round_trip(identity)
    assert restored == identity
    assert restored.generate_key() == identity.generate_key()


def test_api_provider_lands_in_the_client_column():
    serialized = serialize_identity(
        ApiCallIdentity(
            provider="openai",
            model="gpt-x",
            context_fingerprint="cf",
            prompt_fingerprint="pf",
        )
    )
    assert serialized.kind == "api"
    assert serialized.client == "openai"  # provider is denormalized into client
    assert serialized.model == "gpt-x"


def test_api_passthrough_round_trip():
    identity = ApiPassthroughCallIdentity(client="anthropic-subscription", body_fingerprint="bf")
    restored = _round_trip(identity)
    assert restored == identity
    assert restored.generate_key() == identity.generate_key()


def test_api_passthrough_denormalized_columns():
    serialized = serialize_identity(
        ApiPassthroughCallIdentity(client="anthropic-subscription", body_fingerprint="bf")
    )
    assert serialized.kind == "api_passthrough"
    assert serialized.client == "anthropic-subscription"
    assert serialized.model == ""


def test_unknown_kind_on_deserialize_raises():
    with pytest.raises(ValueError):
        deserialize_identity(
            SerializedIdentity(kind="nope", client="c", model="m", effort="", identity_json="{}")
        )
