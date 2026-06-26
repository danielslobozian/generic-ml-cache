# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GatewayResponse — the outcome of a caching gateway call."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayResponse:
    """The result returned to the caller after a gateway cache check or forward.

    ``response_body_bytes`` is the raw Anthropic API response body, either
    retrieved from the blob store on a hit or forwarded from the upstream on a
    miss. ``cache_hit`` distinguishes the two so the caller can set the
    appropriate response header.
    """

    response_body_bytes: bytes
    status_code: int
    cache_hit: bool
