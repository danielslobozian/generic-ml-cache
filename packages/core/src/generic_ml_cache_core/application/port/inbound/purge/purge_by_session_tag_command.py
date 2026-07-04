# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PurgeBySessionTagCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PurgeBySessionTagCommand:
    tag: str
    hard: bool = False
