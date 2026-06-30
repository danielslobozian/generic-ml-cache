# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionKeysForSessionCommand."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionKeysForSessionCommand:
    """The distinct execution keys recorded under ``session_id``."""

    session_id: str
