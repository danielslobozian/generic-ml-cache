# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""TotalStoredBytesUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class TotalStoredBytesUseCase(ABC):
    """Inbound port: total stored artifact bytes across current executions."""

    @abstractmethod
    def total_stored_bytes(self) -> int: ...
