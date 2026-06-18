# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""--stream: an opt-in live NDJSON progress file.

Display-only. It never changes the recorded cassette or the cache key (stream_path
is not part of a Request), and switching the clients to streaming output mode must
reconstruct the same answer+usage as the old single-object form.
"""

from __future__ import annotations

import json
from pathlib import Path

from generic_ml_cache import get_adapter
from generic_ml_cache.cli import main
from generic_ml_cache.stream import StreamWriter


def _events(path) -> list:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def test_writer_appends_ndjson(tmp_path):
    f = tmp_path / "s.jsonl"
    w = StreamWriter(f)
    w.event("start", client="claude")
    w.event("thinking")
    w.close()
    evs = _events(f)
    assert [e["kind"] for e in evs] == ["start", "thinking"]
    assert evs[0]["client"] == "claude" and "ts" in evs[0]


def test_writer_is_best_effort_on_bad_path():
    # An unwritable path disables streaming silently -- never raises.
    w = StreamWriter(Path("/proc/cannot/possibly/exist.jsonl"))
    w.event("start")
    w.close()


# --- reconstruction: stream form parses identically to the single object ------


def test_claude_parse_identical_stream_vs_single():
    obj = {
        "type": "result",
        "subtype": "success",
        "result": "hi",
        "usage": {
            "input_tokens": 3,
            "output_tokens": 5,
            "cache_read_input_tokens": 1,
            "cache_creation_input_tokens": 2,
        },
        "total_cost_usd": 0.01,
    }
    single = json.dumps(obj)
    stream = "\n".join(
        [
            json.dumps({"type": "system", "subtype": "init"}),
            json.dumps({"type": "stream_event", "event": {"type": "message_start"}}),
            single,
        ]
    )
    a = get_adapter("claude").parse_output(single)
    b = get_adapter("claude").parse_output(stream)
    assert a.text == b.text == "hi"
    assert a.usage.input_tokens == b.usage.input_tokens == 3
    assert a.usage.output_tokens == b.usage.output_tokens == 5
    assert a.usage.cost_usd == b.usage.cost_usd == 0.01


def test_cursor_parse_identical_stream_vs_single():
    obj = {
        "type": "result",
        "subtype": "success",
        "result": "hi",
        "usage": {"inputTokens": 3, "outputTokens": 5, "cacheReadTokens": 1, "cacheWriteTokens": 0},
    }
    single = json.dumps(obj)
    stream = "\n".join(
        [
            json.dumps({"type": "system", "subtype": "init", "model": "m"}),
            json.dumps(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}}
            ),
            single,
        ]
    )
    a = get_adapter("cursor").parse_output(single)
    b = get_adapter("cursor").parse_output(stream)
    assert a.text == b.text == "hi"
    assert a.usage.input_tokens == b.usage.input_tokens == 3
    assert a.usage.output_tokens == b.usage.output_tokens == 5


# --- per-client event normalization ------------------------------------------


def test_claude_stream_event_normalization():
    cl = get_adapter("claude")
    assert cl.stream_event(json.dumps({"type": "system", "subtype": "init"})) == {"kind": "start"}
    assert cl.stream_event(json.dumps({"type": "system", "subtype": "thinking_tokens"})) == {
        "kind": "thinking"
    }
    tool = {
        "type": "stream_event",
        "event": {
            "type": "content_block_start",
            "content_block": {"type": "tool_use", "name": "web_search"},
        },
    }
    assert cl.stream_event(json.dumps(tool)) == {"kind": "tool", "name": "web_search"}
    assert cl.stream_event(json.dumps({"type": "result"})) == {"kind": "result"}
    assert cl.stream_event("not json") is None


def test_codex_and_cursor_stream_event_normalization():
    co = get_adapter("codex")
    assert co.stream_event(json.dumps({"type": "thread.started"})) == {"kind": "start"}
    assert co.stream_event(json.dumps({"type": "turn.completed", "usage": {}})) == {
        "kind": "result"
    }
    assert co.stream_event(
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "x"}})
    ) == {"kind": "message"}
    cu = get_adapter("cursor")
    assert cu.stream_event(json.dumps({"type": "system", "subtype": "init"})) == {"kind": "start"}
    assert cu.stream_event(json.dumps({"type": "result"})) == {"kind": "result"}


# --- end to end through the runner (exercises the incremental reader path) ----

_CLI = ["--client", "fake", "--model", "m", "--effort", "high"]


def test_stream_flag_writes_event_file_end_to_end(tmp_path):
    sf = tmp_path / "live.jsonl"
    rc = main(["run", *_CLI, "--prompt", "STDOUT hello", "--stream", str(sf)])
    assert rc == 0
    kinds = [e["kind"] for e in _events(sf)]
    assert kinds[0] == "run.start"
    assert kinds[-1] == "run.end"
    assert _events(sf)[0]["client"] == "fake"
