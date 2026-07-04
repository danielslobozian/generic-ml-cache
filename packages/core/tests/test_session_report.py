# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for build_session_report (pure aggregation)."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.session.session_event_row import (
    SessionEventRow,
)
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.domain.service.session_report import build_session_report


def _row(ts, event, client, model, key):
    return SessionEventRow(ts=ts, event=event, client=client, model=model, execution_key=key)


EVENTS = [
    _row("2026-06-21T10:00:00+00:00", "record", "claude", "sonnet", "k1"),
    _row("2026-06-21T10:05:00+00:00", "hit", "claude", "sonnet", "k1"),  # saved
    _row("2026-06-22T09:00:00+00:00", "record", "claude", "haiku", "k2"),
    _row("2026-06-22T09:30:00+00:00", "run", "openai", "gpt-x", "k3"),  # no usage -> unknown
    _row("2026-06-23T08:00:00+00:00", "miss", "claude", "sonnet", None),  # invocation only
]
USAGE = {
    "k1": TokenUsage(
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=20,
        cache_write_tokens=5,
        reasoning_tokens=30,
    ),
    "k2": TokenUsage(input_tokens=10, output_tokens=5),
    # k3 absent -> the run reported no usage
}


def _report():
    return build_session_report("sess", EVENTS, USAGE)


def test_headline_counts():
    r = _report()
    assert (r.invocations, r.executions, r.hits) == (5, 3, 1)
    assert r.unknown_usage == 1  # the openai run had no usage


def test_span_covers_multiple_days():
    r = _report()
    assert (r.span_start, r.span_end, r.day_count) == ("2026-06-21", "2026-06-23", 3)


def test_tokens_grouped_by_client_and_model():
    by_model = {(m.client, m.model): m for m in _report().by_model}
    sonnet = by_model[("claude", "sonnet")]
    assert (sonnet.spent_input, sonnet.spent_output, sonnet.spent_tokens) == (100, 50, 150)
    assert sonnet.saved_tokens == 150  # the hit replayed k1's usage
    assert (sonnet.executions, sonnet.hits) == (1, 1)

    haiku = by_model[("claude", "haiku")]
    assert (haiku.spent_tokens, haiku.saved_tokens, haiku.executions) == (15, 0, 1)

    gptx = by_model[("openai", "gpt-x")]
    assert (gptx.spent_tokens, gptx.executions) == (0, 1)  # unknown usage -> 0 tokens, still 1 exec


def test_extended_token_fields_aggregated():
    by_model = {(m.client, m.model): m for m in _report().by_model}
    sonnet = by_model[("claude", "sonnet")]
    assert (sonnet.cache_read_tokens, sonnet.cache_write_tokens, sonnet.reasoning_tokens) == (
        20,
        5,
        30,
    )

    # k2 had no cache/reasoning tokens — should be zero, not error
    haiku = by_model[("claude", "haiku")]
    assert (haiku.cache_read_tokens, haiku.cache_write_tokens, haiku.reasoning_tokens) == (0, 0, 0)

    # unknown usage -> all extended fields are zero
    gptx = by_model[("openai", "gpt-x")]
    assert (gptx.cache_read_tokens, gptx.cache_write_tokens, gptx.reasoning_tokens) == (0, 0, 0)


def test_extended_token_fields_zero_on_empty_session():
    r = build_session_report("nope", [], {})
    assert r.by_model == ()


def test_by_day_is_activity_counts_oldest_first():
    days = _report().by_day
    assert [(d.day, d.invocations, d.executions, d.hits) for d in days] == [
        ("2026-06-21", 2, 1, 1),
        ("2026-06-22", 2, 2, 0),
        ("2026-06-23", 1, 0, 0),  # the miss is an invocation, not an execution or hit
    ]


def test_empty_session():
    r = build_session_report("nope", [], {})
    assert (r.invocations, r.executions, r.hits, r.unknown_usage) == (0, 0, 0, 0)
    assert (r.span_start, r.span_end, r.by_model, r.by_day) == (None, None, (), ())
