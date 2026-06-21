# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Usage envelope: per-client extraction, normalization, storage, degradation.

The client output samples below are faithful to the real JSON each CLI emitted in
its structured mode (captured directly from the live clients). They are the ground
truth the normalization is built against -- not invented shapes.
"""

from __future__ import annotations

import json

from generic_ml_cache.adapter.out.client.registry import get_adapter
from generic_ml_cache.application.domain.model.usage import float_or_none, int_or_none

# --- real client output samples (structured mode) ---------------------------

CLAUDE_JSON = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Caching avoids paying to regenerate identical outputs.",
        "total_cost_usd": 0.0515915,
        "usage": {
            "input_tokens": 3,
            "cache_creation_input_tokens": 7397,
            "cache_read_input_tokens": 16945,
            "output_tokens": 100,
            "service_tier": "standard",
        },
        "modelUsage": {
            "claude-haiku-4-5-20251001": {"inputTokens": 537, "costUSD": 0.000617},
            "claude-sonnet-4-6": {"inputTokens": 3, "costUSD": 0.0509745},
        },
    }
)

# Codex emits a JSON-lines *stream*; the answer and usage are in different events.
CODEX_JSONL = "\n".join(
    [
        json.dumps({"type": "thread.started", "thread_id": "t1"}),
        json.dumps({"type": "turn.started"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "agent_message",
                    "text": "Caching reuses a prior answer.",
                },
            }
        ),
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10818,
                    "cached_input_tokens": 4992,
                    "output_tokens": 88,
                    "reasoning_output_tokens": 32,
                },
            }
        ),
    ]
)

CURSOR_JSON = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Caching cuts compute for repeated requests.",
        "usage": {
            "inputTokens": 10673,
            "outputTokens": 125,
            "cacheReadTokens": 469,
            "cacheWriteTokens": 0,
        },
    }
)


# --- per-client extraction + normalization ----------------------------------


def test_claude_parses_text_and_usage():
    parsed = get_adapter("claude").parse_output(CLAUDE_JSON)
    assert parsed.text == "Caching avoids paying to regenerate identical outputs."
    u = parsed.usage
    assert (u.input_tokens, u.output_tokens) == (3, 100)
    assert u.cache_read_tokens == 16945
    assert u.cache_write_tokens == 7397
    # Claude folds reasoning into output -> not separable -> unknown.
    assert u.reasoning_tokens is None
    # Cost is the cumulative estimate across all models the run used.
    assert u.cost_usd == 0.0515915
    # The per-model breakdown (incl. the subagent model) is kept verbatim in raw.
    assert set(u.raw["modelUsage"]) == {"claude-haiku-4-5-20251001", "claude-sonnet-4-6"}
    assert u.raw["total_cost_usd"] == 0.0515915


def test_codex_parses_stream_text_and_usage():
    parsed = get_adapter("codex").parse_output(CODEX_JSONL)
    assert parsed.text == "Caching reuses a prior answer."
    u = parsed.usage
    assert (u.input_tokens, u.output_tokens) == (10818, 88)
    assert u.cache_read_tokens == 4992
    # Codex reports reasoning *separately* from output.
    assert u.reasoning_tokens == 32
    # Codex reports no cache-write count and no cost -> unknown, not zero.
    assert u.cache_write_tokens is None
    assert u.cost_usd is None


def test_cursor_parses_text_and_usage_with_known_zero():
    parsed = get_adapter("cursor").parse_output(CURSOR_JSON)
    assert parsed.text == "Caching cuts compute for repeated requests."
    u = parsed.usage
    assert (u.input_tokens, u.output_tokens) == (10673, 125)
    assert u.cache_read_tokens == 469
    # Cursor *reported* zero cache-write: a known 0, distinct from Codex's unknown.
    assert u.cache_write_tokens == 0
    assert u.reasoning_tokens is None
    assert u.cost_usd is None


def test_known_zero_is_not_unknown():
    """The whole point of Optional: a reported 0 and an absent field differ."""
    cursor_u = get_adapter("cursor").parse_output(CURSOR_JSON).usage
    codex_u = get_adapter("codex").parse_output(CODEX_JSONL).usage
    assert cursor_u.cache_write_tokens == 0  # reported zero
    assert codex_u.cache_write_tokens is None  # never reported
    assert cursor_u.cache_write_tokens != codex_u.cache_write_tokens


# --- graceful degradation ----------------------------------------------------


def test_adapters_degrade_on_unparseable_output():
    """An unexpected/garbled output must not raise: keep the raw text, drop usage."""
    junk = "not json at all"
    for client in ("claude", "codex", "cursor"):
        parsed = get_adapter(client).parse_output(junk)
        assert parsed.text == junk
        assert parsed.usage is None


def test_claude_degrades_when_result_field_missing():
    parsed = get_adapter("claude").parse_output(json.dumps({"usage": {"input_tokens": 5}}))
    assert parsed.usage is None  # no `result` -> not the shape we trust


def test_codex_degrades_without_agent_message():
    stream = json.dumps({"type": "turn.completed", "usage": {"input_tokens": 1}})
    parsed = get_adapter("codex").parse_output(stream)
    assert parsed.text == stream
    assert parsed.usage is None


# --- coercion helpers --------------------------------------------------------


def test_coercion_helpers_map_absent_to_none_not_zero():
    assert int_or_none(None) is None
    assert int_or_none(7) == 0 + 7
    assert int_or_none("nope") is None
    assert int_or_none(True) is None  # a bool is not a token count
    assert float_or_none(None) is None
    assert float_or_none("1.5") == 1.5


# Cassette round-trip / store end-to-end tests were removed with the cassette
# format in the Phase 5/6 cutover; usage now flows through ClientRunResult ->
# MlExecution -> the SQLite repository, covered by test_sqlite_execution_repository
# and test_composition. The adapter parse_output behaviour above is the part unique
# to this file.
