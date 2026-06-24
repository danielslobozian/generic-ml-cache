# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Serialize a polymorphic CallIdentity for the SQLite repository.

The hybrid persistence (domain-model §3): the queryable fields (kind, client,
model, effort) become real columns; the divergent/opaque fields ride in a JSON
column. This pair maps each CallIdentity subclass to that row shape and back. It
lives in the adapter — the domain identities know nothing about the database.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)


@dataclass(frozen=True)
class SerializedIdentity:
    """The row shape: denormalized query columns + the serialized remainder."""

    kind: str
    client: str
    model: str
    effort: str
    identity_json: str


def serialize_identity(identity: CallIdentity) -> SerializedIdentity:
    if isinstance(identity, ManagedCallIdentity):
        return SerializedIdentity(
            kind=ExecutionKind.LOCAL_MANAGED.value,
            client=identity.client,
            model=identity.model,
            effort=identity.effort,
            identity_json=json.dumps(
                {
                    "context_fingerprint": identity.context_fingerprint,
                    "prompt_fingerprint": identity.prompt_fingerprint,
                    "input_file_fingerprints": identity.input_file_fingerprints,
                    "client_args_fingerprint": identity.client_args_fingerprint,
                    "grants": sorted(identity.grants),
                }
            ),
        )
    if isinstance(identity, PassthroughCallIdentity):
        return SerializedIdentity(
            kind=ExecutionKind.LOCAL_PASSTHROUGH.value,
            client=identity.client,
            model="",
            effort="",
            identity_json=json.dumps({"native_args_fingerprint": identity.native_args_fingerprint}),
        )
    if isinstance(identity, ApiCallIdentity):
        return SerializedIdentity(
            kind=ExecutionKind.API.value,
            client=identity.provider,
            model=identity.model,
            effort=identity.effort,
            identity_json=json.dumps(
                {
                    "context_fingerprint": identity.context_fingerprint,
                    "prompt_fingerprint": identity.prompt_fingerprint,
                    "system_fingerprint": identity.system_fingerprint,
                }
            ),
        )
    raise ValueError(f"cannot serialize unknown call identity type: {type(identity).__name__}")


def deserialize_identity(serialized: SerializedIdentity) -> CallIdentity:
    fields = json.loads(serialized.identity_json)
    if serialized.kind == ExecutionKind.LOCAL_MANAGED.value:
        return ManagedCallIdentity(
            client=serialized.client,
            model=serialized.model,
            effort=serialized.effort,
            context_fingerprint=fields["context_fingerprint"],
            prompt_fingerprint=fields["prompt_fingerprint"],
            input_file_fingerprints=dict(fields["input_file_fingerprints"]),
            client_args_fingerprint=fields["client_args_fingerprint"],
            grants=frozenset(fields["grants"]),
        )
    if serialized.kind == ExecutionKind.LOCAL_PASSTHROUGH.value:
        return PassthroughCallIdentity(
            client=serialized.client,
            native_args_fingerprint=fields["native_args_fingerprint"],
        )
    if serialized.kind == ExecutionKind.API.value:
        return ApiCallIdentity(
            provider=serialized.client,
            model=serialized.model,
            context_fingerprint=fields["context_fingerprint"],
            prompt_fingerprint=fields["prompt_fingerprint"],
            system_fingerprint=fields.get("system_fingerprint"),
            effort=serialized.effort,
        )
    raise ValueError(f"cannot deserialize unknown identity kind: {serialized.kind!r}")
