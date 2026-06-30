# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FindCurrentExecutionCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FindCurrentExecutionCommand:
    """Look up the current cached execution for ``execution_key``."""

    execution_key: str
