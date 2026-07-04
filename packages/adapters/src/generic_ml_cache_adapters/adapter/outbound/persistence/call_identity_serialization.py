# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Serialize a polymorphic CallIdentity for the SQLite repository.

The hybrid persistence (domain-model §3): the queryable fields (kind, client,
model, effort) become real columns; the divergent/opaque fields ride in a JSON
column. The subclass ⇄ field mapping itself lives in the domain now (the opaque
``serialize_call_identity`` codec, W21); this adapter only projects that one
self-contained string onto the row shape — it reads the denormalized query columns
straight off the codec's fields instead of re-deriving them per kind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.identity.identity_codec import (
    deserialize_call_identity,
    serialize_call_identity,
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
    payload = serialize_call_identity(identity)
    columns = json.loads(payload)
    return SerializedIdentity(
        kind=str(columns["kind"]),
        client=str(columns["client"]),
        model=str(columns.get("model", "")),
        effort=str(columns.get("effort", "")),
        identity_json=payload,
    )


def deserialize_identity(serialized: SerializedIdentity) -> CallIdentity:
    return deserialize_call_identity(serialized.identity_json)
