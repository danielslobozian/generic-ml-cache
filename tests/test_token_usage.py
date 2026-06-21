# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for TokenUsage."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.usage.token_usage import TokenUsage


def test_all_fields_default_to_none():
    token_usage = TokenUsage()
    assert token_usage.input_tokens is None
    assert token_usage.output_tokens is None
    assert token_usage.cache_read_tokens is None
    assert token_usage.cache_write_tokens is None
    assert token_usage.reasoning_tokens is None
    assert token_usage.cost_usd is None
    assert token_usage.raw == {}


def test_to_dict_round_trip():
    token_usage = TokenUsage(
        input_tokens=100,
        output_tokens=42,
        cache_read_tokens=500,
        cache_write_tokens=None,
        reasoning_tokens=8,
        cost_usd=0.0125,
        raw={"model": "claude-sonnet-4-6", "cost": 0.012},
    )
    reloaded = TokenUsage.from_dict(token_usage.to_dict())
    assert reloaded == token_usage


def test_from_dict_coerces_string_int():
    token_usage = TokenUsage.from_dict({"input_tokens": "99", "output_tokens": "10"})
    assert token_usage.input_tokens == 99
    assert token_usage.output_tokens == 10


def test_from_dict_absent_field_is_none_not_zero():
    token_usage = TokenUsage.from_dict({"input_tokens": 10})
    assert token_usage.cache_write_tokens is None


def test_from_dict_reported_zero_is_not_none():
    token_usage = TokenUsage.from_dict({"cache_write_tokens": 0})
    assert token_usage.cache_write_tokens == 0


def test_from_dict_bool_is_not_a_token_count():
    token_usage = TokenUsage.from_dict({"input_tokens": True})
    assert token_usage.input_tokens is None


def test_from_dict_preserves_raw_block():
    raw_block = {"modelUsage": {"claude-sonnet-4-6": {"costUSD": 0.05}}}
    token_usage = TokenUsage.from_dict({"raw": raw_block})
    assert token_usage.raw == raw_block


def test_is_frozen():
    token_usage = TokenUsage(input_tokens=1)
    with pytest.raises(Exception):
        token_usage.input_tokens = 2  # type: ignore[misc]
