# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""HitCountsByKeyUseCase (inbound port)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class HitCountsByKeyUseCase(ABC):
    """Inbound port: {execution_key: hit_count} across all HIT events."""

    @abstractmethod
    def hit_counts_by_key(self) -> dict[str, int]: ...
