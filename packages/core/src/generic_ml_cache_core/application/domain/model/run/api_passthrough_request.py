# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ApiPassthroughRequest — what core passes to an ApiPassthroughRunnerPort relay."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

_NO_HEADERS: Mapping[str, str] = MappingProxyType({})


@dataclass(frozen=True)
class ApiPassthroughRequest:
    """Application-level description of a verbatim API-passthrough relay call.

    The relay is opaque: gmlcache does not model the request, only forwards the
    raw body bytes to the upstream endpoint and returns the raw response. Only the
    body is keyed (its digest is the cache identity); ``forward_headers`` carry the
    caller's auth verbatim and are never keyed or stored. The upstream endpoint is
    operator-configured on the adapter, so no URL travels here.
    """

    raw_body: bytes = b""
    forward_headers: Mapping[str, str] = field(default=_NO_HEADERS)
    timeout: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "forward_headers", MappingProxyType(dict(self.forward_headers)))
