# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PurgeByKeyCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PurgeByKeyCommand:
    execution_key: str
    hard: bool = False
