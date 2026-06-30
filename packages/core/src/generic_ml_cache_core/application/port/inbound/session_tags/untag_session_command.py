# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""UntagSessionCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UntagSessionCommand:
    """Detach ``tag`` from ``session_id`` (no-op when absent)."""

    session_id: str
    tag: str
