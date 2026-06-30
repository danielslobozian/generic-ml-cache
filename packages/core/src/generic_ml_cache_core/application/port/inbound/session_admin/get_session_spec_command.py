# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""GetSessionSpecCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GetSessionSpecCommand:
    """Read the execution spec attached to ``session_id`` (None if absent)."""

    session_id: str
