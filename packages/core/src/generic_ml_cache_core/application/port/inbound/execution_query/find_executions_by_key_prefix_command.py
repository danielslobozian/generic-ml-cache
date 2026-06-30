# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FindExecutionsByKeyPrefixCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FindExecutionsByKeyPrefixCommand:
    """Find current executions whose key starts with ``key_prefix``."""

    key_prefix: str
