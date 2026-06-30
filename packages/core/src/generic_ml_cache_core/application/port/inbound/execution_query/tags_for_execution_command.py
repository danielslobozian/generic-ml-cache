# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""TagsForExecutionCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TagsForExecutionCommand:
    """The tags on the current execution for ``execution_key``."""

    execution_key: str
