# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ApiPassthroughCallIdentity."""

from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.common.checksum import checksum_input_data


@dataclass(frozen=True)
class ApiPassthroughCallIdentity(CallIdentity):
    """The identity of a verbatim API-passthrough relay call.

    A passthrough relay is opaque: gmlcache does not decompose the request, only
    forwards its raw bytes. So the identity is the relay client plus a *fingerprint*
    of those bytes — the raw body may carry secrets and is never keyed or stored,
    only its digest. The kind is folded into the key, so a relay call can never
    collide with a structured API call to the same provider.
    """

    client: str
    body_fingerprint: str

    def generate_key(self) -> str:
        return checksum_input_data(
            {
                "kind": ExecutionKind.API_PASSTHROUGH.value,
                "client": self.client,
                "body": self.body_fingerprint,
            }
        )

    @property
    def summary_client(self) -> str:
        return self.client

    @property
    def summary_model(self) -> str:
        return ""
