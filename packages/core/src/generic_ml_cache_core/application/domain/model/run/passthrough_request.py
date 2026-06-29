# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PassthroughRequest — what core passes to a LocalClientPort for passthrough execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class PassthroughRequest:
    """Application-level description of a passthrough local execution.

    The local client is invoked almost as if the user called it directly:
    native_args are forwarded verbatim to the executable. No workspace isolation,
    no artifact capture, no config rewriting.
    """

    native_args: List[str] = field(default_factory=list)
    timeout: Optional[float] = None
