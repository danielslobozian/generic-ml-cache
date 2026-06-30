# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClearSessionSpecCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClearSessionSpecCommand:
    """Remove any execution spec attached to ``session_id``."""

    session_id: str
