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

    **The auth/session is DELIBERATELY excluded from the key (X4, single-user).** The
    forwarded subscription token and any ``session_id`` are NOT part of the identity,
    on purpose: this is a single-user LOCAL tool (never multi-tenant — see the
    threat model), so there is no cross-principal leak to guard against; and the
    caller's OAuth token *refreshes over time*, so folding it into the key would
    fragment the cache and force a needless upstream call on every refresh. Body-only
    keying is therefore REQUIRED for cross-session cache hits, not merely acceptable —
    do NOT "fix" this by adding the token/session to the key. The one residual risk is
    accidental network exposure, handled by not opening the port (the daemon binds
    localhost by default) + a security note, never by changing this key.
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
