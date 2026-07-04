# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ApiPassthroughCallIdentity."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.api_passthrough_call_identity import (
    ApiPassthroughCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity


def test_is_a_call_identity():
    assert isinstance(
        ApiPassthroughCallIdentity(client="anthropic-subscription", body_fingerprint="fp"),
        CallIdentity,
    )


def test_generate_key_is_hex_and_deterministic():
    identity = ApiPassthroughCallIdentity(client="anthropic-subscription", body_fingerprint="fp")
    key = identity.generate_key()
    assert len(key) == 64
    assert key == identity.generate_key()


def test_different_clients_produce_different_keys():
    first = ApiPassthroughCallIdentity(client="a", body_fingerprint="fp").generate_key()
    second = ApiPassthroughCallIdentity(client="b", body_fingerprint="fp").generate_key()
    assert first != second


def test_different_bodies_produce_different_keys():
    first = ApiPassthroughCallIdentity(client="a", body_fingerprint="one").generate_key()
    second = ApiPassthroughCallIdentity(client="a", body_fingerprint="two").generate_key()
    assert first != second


def test_summary_reports_client_and_no_model():
    identity = ApiPassthroughCallIdentity(client="anthropic-subscription", body_fingerprint="fp")
    assert identity.summary_client == "anthropic-subscription"
    assert identity.summary_model == ""


def test_never_collides_with_a_structured_api_key():
    """The kind is folded into the key, so a verbatim relay call and a structured
    API call to the same provider can never hit each other in the shared repository."""
    relay = ApiPassthroughCallIdentity(client="anthropic", body_fingerprint="x").generate_key()
    structured = ApiCallIdentity(
        provider="anthropic",
        model="",
        context_fingerprint="",
        prompt_fingerprint="x",
        system_fingerprint=None,
        effort="",
    ).generate_key()
    assert relay != structured
