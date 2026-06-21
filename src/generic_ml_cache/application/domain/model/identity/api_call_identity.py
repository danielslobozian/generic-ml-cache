# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ApiCallIdentity."""

from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache.common.checksum import checksum_input_data


@dataclass(frozen=True)
class ApiCallIdentity(CallIdentity):
    """The identity of a direct API call.

    Addressed by provider, model, and a fingerprint of the full message list —
    the raw messages may carry sensitive context and are never keyed or stored,
    only their digest. The kind is folded into the key, so an API call can never
    collide with a local managed or passthrough call.
    """

    provider: str
    model: str
    messages_fingerprint: str

    def generate_key(self) -> str:
        return checksum_input_data(
            {
                "kind": ExecutionKind.API.value,
                "provider": self.provider,
                "model": self.model,
                "messages": self.messages_fingerprint,
            }
        )
