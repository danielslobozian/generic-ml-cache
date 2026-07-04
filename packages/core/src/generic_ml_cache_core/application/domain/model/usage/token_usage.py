# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""TokenUsage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from generic_ml_cache_core.application.domain.model.usage.usage import float_or_none, int_or_none
from generic_ml_cache_core.common.immutable import deep_freeze, thaw


@dataclass(frozen=True)
class TokenUsage:
    """Normalized token counts for one ML execution, with the raw block kept.

    The stored counterpart of :class:`Usage`: same counts, but the database-bound
    domain type (parse-at-edge :class:`Usage` → stored ``TokenUsage``); the two are
    distinct layers, not a duplication.

    Accounting data: database-bound, separate from the output artifacts.
    Every count is Optional[int]: a value the client reported, or None when it
    did not report that field at all. None means unknown, never zero.
    cost_usd is the client's own advisory estimate; never derived by gmlcache.
    raw preserves the client's verbatim usage structure losslessly.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    cost_usd: float | None = None
    raw: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "raw", deep_freeze(self.raw))

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cost_usd": self.cost_usd,
            "raw": thaw(self.raw),
        }

    @classmethod
    def from_dict(cls, token_usage_dict: dict[str, Any]) -> TokenUsage:
        return cls(
            input_tokens=int_or_none(token_usage_dict.get("input_tokens")),
            output_tokens=int_or_none(token_usage_dict.get("output_tokens")),
            cache_read_tokens=int_or_none(token_usage_dict.get("cache_read_tokens")),
            cache_write_tokens=int_or_none(token_usage_dict.get("cache_write_tokens")),
            reasoning_tokens=int_or_none(token_usage_dict.get("reasoning_tokens")),
            cost_usd=float_or_none(token_usage_dict.get("cost_usd")),
            raw=dict(token_usage_dict.get("raw", {})),
        )
