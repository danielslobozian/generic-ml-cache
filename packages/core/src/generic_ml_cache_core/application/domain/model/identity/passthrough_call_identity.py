# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PassthroughCallIdentity."""

from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.common.checksum import checksum_input_data


@dataclass(frozen=True)
class PassthroughCallIdentity(CallIdentity):
    """The identity of a passthrough (alias) call.

    A passthrough is opaque: gmlcache does not model its inputs, only forwards the
    native argument tail to the client. So the identity is just the client plus a
    *fingerprint* of those native args — the raw args may carry secrets and are
    never keyed or stored, only their digest. The kind is folded into the key, so
    a passthrough can never collide with a managed call.
    """

    client: str
    native_args_fingerprint: str

    def generate_key(self) -> str:
        return checksum_input_data(
            {
                "kind": ExecutionKind.LOCAL_PASSTHROUGH.value,
                "client": self.client,
                "args": self.native_args_fingerprint,
            }
        )

    @property
    def summary_client(self) -> str:
        return self.client

    @property
    def summary_model(self) -> str:
        return ""
