# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PurgeAllCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PurgeAllCommand:
    hard: bool = False
