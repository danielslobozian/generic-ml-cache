# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from generic_ml_cache_core.application.domain.model.identity.gateway_call_identity import (
    GatewayCallIdentity,
)


def test_generate_key_returns_cache_key():
    identity = GatewayCallIdentity(cache_key="abc123")
    assert identity.generate_key() == "abc123"
