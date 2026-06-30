# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PurgeByTagCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PurgeByTagCommand:
    tag: str
    hard: bool = False
