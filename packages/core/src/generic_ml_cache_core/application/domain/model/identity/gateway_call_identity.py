# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GatewayCallIdentity — call identity for a passthrough gateway request."""

from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity


@dataclass(frozen=True)
class GatewayCallIdentity(CallIdentity):
    """Identity whose key is the pre-computed SHA-256 of the gateway request.

    The gateway hashes the full request (model + messages + system) in
    GatewayRequest.generate_cache_key(); this identity wraps that digest so
    the blob store key and the repository key are always identical.
    """

    cache_key: str

    def generate_key(self) -> str:
        return self.cache_key

    @property
    def summary_client(self) -> str:
        # The gateway request carries the provider, but this digest-only identity
        # does not; the shipped gateway is Anthropic-shaped, matching the store's
        # denormalized column. (Kept in parity with the persistence serializer.)
        return "anthropic"

    @property
    def summary_model(self) -> str:
        return ""
