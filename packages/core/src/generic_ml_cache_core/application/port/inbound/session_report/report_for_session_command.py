# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ReportForSessionCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportForSessionCommand:
    """Roll up the activity of a single session."""

    session_id: str
