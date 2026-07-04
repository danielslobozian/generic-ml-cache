# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""TagSessionCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TagSessionCommand:
    """Attach ``tag`` to ``session_id``."""

    session_id: str
    tag: str
