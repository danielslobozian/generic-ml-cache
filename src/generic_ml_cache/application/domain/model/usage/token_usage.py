# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""TokenUsage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from generic_ml_cache.application.domain.model.usage.usage import float_or_none, int_or_none


@dataclass(frozen=True)
class TokenUsage:
    """Normalized token counts for one ML execution, with the raw block kept.

    Accounting data: database-bound, separate from the output artifacts.
    Every count is Optional[int]: a value the client reported, or None when it
    did not report that field at all. None means unknown, never zero.
    cost_usd is the client's own advisory estimate; never derived by gmlcache.
    raw preserves the client's verbatim usage structure losslessly.
    """

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": self.cost_usd,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, token_usage_dict: Dict[str, Any]) -> "TokenUsage":
        return cls(
            input_tokens=int_or_none(token_usage_dict.get("input_tokens")),
            output_tokens=int_or_none(token_usage_dict.get("output_tokens")),
            cache_read_tokens=int_or_none(token_usage_dict.get("cache_read_tokens")),
            cache_write_tokens=int_or_none(token_usage_dict.get("cache_write_tokens")),
            reasoning_tokens=int_or_none(token_usage_dict.get("reasoning_tokens")),
            cost_usd=float_or_none(token_usage_dict.get("cost_usd")),
            raw=dict(token_usage_dict.get("raw", {})),
        )
