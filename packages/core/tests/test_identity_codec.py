# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The opaque CallIdentity round-trip codec (W21).

An embedder round-trips a CallIdentity through a single opaque string, using only
the public ``serialize_call_identity`` / ``deserialize_call_identity`` pair — never
the four concrete subclasses.
"""

from __future__ import annotations

import pytest

from generic_ml_cache_core import deserialize_call_identity, serialize_call_identity
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

_IDENTITIES = [
    ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="ctx",
        prompt_fingerprint="prompt",
        input_file_fingerprints={"/src/a.py": "sha_a", "/src/b.py": "sha_b"},
        client_args_fingerprint="args",
        grants=frozenset({"net", "read"}),
    ),
    # A managed identity exercising EVERY key-determining field — system_fingerprint
    # and allow_paths were silently dropped by the previous hand-listed serializer,
    # changing generate_key on read-back; the generic field codec preserves them.
    ManagedCallIdentity(
        client="claude",
        model="opus",
        effort="",
        context_fingerprint="ctx2",
        prompt_fingerprint="p2",
        system_fingerprint="sys",
        allow_paths=frozenset({"/repo/a", "/repo/b"}),
    ),
    PassthroughCallIdentity(client="codex", native_args_fingerprint="fp"),
    ApiCallIdentity(
        provider="openai",
        model="gpt-x",
        context_fingerprint="cf",
        prompt_fingerprint="pf",
        system_fingerprint="sf",
        effort="high",
    ),
    ApiPassthroughCallIdentity(client="anthropic-subscription", body_fingerprint="bf"),
]


@pytest.mark.parametrize("identity", _IDENTITIES, ids=lambda i: type(i).__name__)
def test_round_trip_preserves_equality_and_key(identity):
    restored = deserialize_call_identity(serialize_call_identity(identity))
    assert restored == identity
    assert restored.generate_key() == identity.generate_key()


def test_serialized_form_is_an_opaque_string():
    payload = serialize_call_identity(_IDENTITIES[0])
    assert isinstance(payload, str)


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        deserialize_call_identity('{"kind": "not-a-real-kind"}')
