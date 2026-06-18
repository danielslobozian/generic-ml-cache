# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Usage envelope: per-client extraction, normalization, storage, degradation.

The client output samples below are faithful to the real JSON each CLI emitted in
its structured mode (captured directly from the live clients). They are the ground
truth the normalization is built against -- not invented shapes.
"""

from __future__ import annotations

import json

from generic_ml_cache.adapters.registry import get_adapter
from generic_ml_cache.cassette import SCHEMA_VERSION, Cassette, Response
from generic_ml_cache.usage import Usage, float_or_none, int_or_none

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


# --- storage: schema v2 round-trip + back-compat with v1 ---------------------


def test_usage_survives_cassette_round_trip():
    usage = Usage(
        input_tokens=3,
        output_tokens=100,
        cache_read_tokens=16945,
        cache_write_tokens=7397,
        reasoning_tokens=None,
        cost_usd=0.0515915,
        raw={"modelUsage": {"claude-sonnet-4-6": {"costUSD": 0.05}}},
    )
    cassette = Cassette(
        client="claude",
        model="sonnet",
        effort="",
        input_data={"context": "", "prompt": "hi"},
        response=Response(stdout="hi there", usage=usage),
    )
    reloaded = Cassette.from_json(cassette.to_json())
    assert reloaded.schema_version == SCHEMA_VERSION == 2
    ru = reloaded.response.usage
    assert ru.input_tokens == 3
    assert ru.cache_write_tokens == 7397
    assert ru.reasoning_tokens is None
    assert ru.cost_usd == 0.0515915
    assert ru.raw["modelUsage"]["claude-sonnet-4-6"]["costUSD"] == 0.05


def test_pre_usage_cassette_loads_with_unknown_usage():
    """A schema-1 cassette (no usage key) must still load -> usage is None."""
    legacy = {
        "schema_version": 1,
        "client": "claude",
        "model": "sonnet",
        "effort": "",
        "input_checksum": "ignored-recomputed",
        "input_data": {"context": "", "prompt": "hi"},
        "response": {"stdout": "hi", "stderr": "", "exit": 0, "files": []},
    }
    cassette = Cassette.from_json(json.dumps(legacy))
    assert cassette.response.usage is None
    assert cassette.response.stdout == "hi"


# --- end-to-end: usage flows launcher -> cassette -> store -------------------


def test_usage_is_captured_and_persisted_end_to_end(store):
    """A real (fake) call's parsed usage lands in the stored cassette and reloads."""
    import sys
    from typing import List

    from generic_ml_cache import register
    from generic_ml_cache.adapters.base import ClientAdapter
    from generic_ml_cache.cache import Mode, Request, resolve
    from generic_ml_cache.usage import ParsedOutput, Usage

    class JsonFakeAdapter(ClientAdapter):
        name = "json_fake"
        default_executable = sys.executable

        def build_argv(
            self,
            executable,
            run_dir,
            model,
            effort,
            context,
            prompt,
            system_prompt,
            client_args=(),
            grants=(),
        ) -> List[str]:
            return [executable, "-c", "print('the answer')"]

        def parse_output(self, stdout: str) -> ParsedOutput:
            # Pretend stdout was structured: hand back clean text + a usage block.
            return ParsedOutput(
                text=stdout.strip(),
                usage=Usage(input_tokens=42, output_tokens=7, cache_read_tokens=0, cost_usd=0.001),
            )

    register(JsonFakeAdapter())
    request = Request(client="json_fake", model="m", effort="", context="", prompt="go")
    outcome = resolve(request, store, mode=Mode.CACHE)

    assert outcome.recorded is True
    assert outcome.response.stdout == "the answer"
    assert outcome.response.usage.input_tokens == 42

    # And it survives a reload from disk (not just the in-memory object).
    reloaded = store.lookup("json_fake", "m", "", request.input_data)
    assert reloaded.response.usage.output_tokens == 7
    assert reloaded.response.usage.cost_usd == 0.001


# --- CLI readouts: inspect shows usage; stats shows tokens saved -------------

import sys as _sys  # noqa: E402

from generic_ml_cache import register as _register  # noqa: E402
from generic_ml_cache.adapters.base import ClientAdapter as _ClientAdapter  # noqa: E402
from generic_ml_cache.cli import main as _main  # noqa: E402
from generic_ml_cache.usage import ParsedOutput as _ParsedOutput  # noqa: E402


class _UsageCliFake(_ClientAdapter):
    """A fake client that emits structured output carrying usage, so the CLI
    readouts can be exercised through a real record + replay."""

    name = "usage_cli_fake"
    default_executable = _sys.executable

    def build_argv(
        self,
        executable,
        run_dir,
        model,
        effort,
        context,
        prompt,
        system_prompt,
        client_args=(),
        grants=(),
    ):
        doc = json.dumps({"result": "hi", "u": {"in": 100, "out": 10, "cr": 5, "cost": 0.002}})
        return [executable, "-c", f"print({doc!r})"]

    def parse_output(self, stdout):
        doc = json.loads(stdout)
        u = doc["u"]
        return _ParsedOutput(
            text=doc["result"],
            usage=Usage(
                input_tokens=u["in"],
                output_tokens=u["out"],
                cache_read_tokens=u["cr"],
                cost_usd=u["cost"],
            ),
        )


_register(_UsageCliFake())


def test_stats_shows_tokens_saved(capsys):
    args = ["run", "--client", "usage_cli_fake", "--model", "m", "--effort", "", "--prompt", "go"]
    assert _main(args) == 0  # fresh record
    assert _main(args) == 0  # identical call -> a replay (hit)
    capsys.readouterr()

    assert _main(["stats"]) == 0
    out = capsys.readouterr().out
    assert "from 1 replay" in out
    assert "input 100" in out  # one replay saved the recorded 100 input tokens
    assert "$0.0020" in out  # cost estimate, summed across replays


def test_stats_json_includes_tokens_saved(capsys):
    args = ["run", "--client", "usage_cli_fake", "--model", "m2", "--effort", "", "--prompt", "go"]
    assert _main(args) == 0
    assert _main(args) == 0
    capsys.readouterr()
    assert _main(["stats", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tokens_saved"]["replays"] == 1
    assert data["tokens_saved"]["input_tokens"] == 100
    assert data["tokens_saved"]["cost_usd"] == 0.002


def test_inspect_shows_usage_and_raw_on_demand(capsys, tmp_path):
    usage = Usage(
        input_tokens=3,
        output_tokens=100,
        cache_read_tokens=16945,
        cache_write_tokens=7397,
        cost_usd=0.0515915,
        raw={"modelUsage": {"claude-sonnet-4-6": {"costUSD": 0.05}}},
    )
    cassette = Cassette(
        client="claude",
        model="sonnet",
        effort="",
        input_data={"context": "", "prompt": "hi"},
        response=Response(stdout="hi", usage=usage),
    )
    path = tmp_path / "c.json"
    path.write_text(cassette.to_json(), encoding="utf-8")

    assert _main(["inspect", str(path)]) == 0
    out = capsys.readouterr().out
    assert "input=3" in out and "cache-write=7397" in out
    assert "client estimate" in out
    assert "modelUsage" not in out  # raw block hidden without --raw

    assert _main(["inspect", "--raw", str(path)]) == 0
    raw_out = capsys.readouterr().out
    assert "modelUsage" in raw_out


def test_inspect_reports_no_usage_cleanly(capsys, tmp_path):
    cassette = Cassette(
        client="fake",
        model="m",
        effort="",
        input_data={"context": "", "prompt": "hi"},
        response=Response(stdout="hi"),  # no usage
    )
    path = tmp_path / "c.json"
    path.write_text(cassette.to_json(), encoding="utf-8")
    assert _main(["inspect", str(path)]) == 0
    assert "(none captured)" in capsys.readouterr().out
