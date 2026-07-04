# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ReportForTagCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportForTagCommand:
    """Roll up the activity of every session carrying ``tag``."""

    tag: str
