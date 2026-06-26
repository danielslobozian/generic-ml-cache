# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ForwardedResponse - the raw result from forwarding a request to the upstream API."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForwardedResponse:
    """The raw bytes and status returned by the upstream after a cache miss.

    Error responses from the upstream (non-200) are also captured here so the
    gateway can forward them verbatim to the caller rather than hiding them
    behind a local exception.
    """

    body_bytes: bytes
    status_code: int
