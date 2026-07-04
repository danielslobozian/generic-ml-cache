# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Opaque round-trip codec for a polymorphic CallIdentity (W21).

``CallIdentity`` is part of the public surface, but its four concrete subclasses
are not — an embedder that receives a ``CallIdentity`` on a port (via
``MlExecution.call_identity``) and needs to persist it must be able to round-trip
it WITHOUT importing those subclasses. This pair is that opaque bridge: an identity
becomes one self-contained string and back.

The mapping is GENERIC over the identity's dataclass fields (never a hand-listed
per-kind field set — that silently drops a field the moment an identity grows one,
corrupting its key). The wire form also carries the denormalized ``kind`` /
``client`` / ``model`` / ``effort`` a persistence adapter columns off, so the
adapter projects the row shape from this one string instead of re-deriving it.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from typing import Any, cast

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.api_passthrough_call_identity import (
    ApiPassthroughCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)

_KIND_BY_TYPE: dict[type[CallIdentity], str] = {
    ManagedCallIdentity: ExecutionKind.LOCAL_MANAGED.value,
    PassthroughCallIdentity: ExecutionKind.LOCAL_PASSTHROUGH.value,
    ApiCallIdentity: ExecutionKind.API.value,
    ApiPassthroughCallIdentity: ExecutionKind.API_PASSTHROUGH.value,
}
_TYPE_BY_KIND: dict[str, type[CallIdentity]] = {v: k for k, v in _KIND_BY_TYPE.items()}


def _jsonable(value: object) -> object:
    """Make a dataclass field value JSON-serialisable (Mapping → dict, set → sorted
    list); scalars and ``None`` pass through. Sets/mappings are sorted so the string
    is stable for a given identity."""
    if isinstance(value, Mapping):
        return dict(cast("Mapping[str, str]", value))
    if isinstance(value, (frozenset, set)):
        return sorted(cast("frozenset[str]", value))
    return value


def serialize_call_identity(identity: CallIdentity) -> str:
    """Serialize a CallIdentity to an opaque, self-contained string. An embedder that
    persists a CallIdentity received on a port round-trips it through this pair
    without importing the four concrete subclasses (W21)."""
    kind = _KIND_BY_TYPE.get(type(identity))
    if kind is None:
        raise ValueError(f"cannot serialize unknown call identity type: {type(identity).__name__}")
    # identity is always a concrete (dataclass) subclass at runtime; the base ABC is
    # not itself a dataclass, so fields() needs the runtime instance.
    fields = {
        f.name: _jsonable(getattr(identity, f.name))
        for f in dataclasses.fields(cast("Any", identity))
    }
    return json.dumps(
        {
            "kind": kind,
            # Denormalized columns a persistence adapter reads without re-deriving:
            "client": identity.summary_client,
            "model": identity.summary_model,
            "effort": str(fields.get("effort", "")),
            "fields": fields,  # the full field set, for lossless reconstruction
        }
    )


def deserialize_call_identity(data: str) -> CallIdentity:
    """Reconstruct a CallIdentity from the string produced by ``serialize_call_identity``."""
    payload: Any = json.loads(data)
    cls = _TYPE_BY_KIND.get(payload.get("kind"))
    if cls is None:
        raise ValueError(f"cannot deserialize unknown identity kind: {payload.get('kind')!r}")
    names = {f.name for f in dataclasses.fields(cast("Any", cls))}
    kwargs = {k: v for k, v in payload.get("fields", {}).items() if k in names}
    return cls(**kwargs)
