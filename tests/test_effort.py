# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from pathlib import Path

from generic_ml_cache.adapter.out.client.claude import ClaudeAdapter
from generic_ml_cache.adapter.out.client.codex import CodexAdapter
from generic_ml_cache.adapter.out.client.cursor import CursorAdapter
from generic_ml_cache.cli import build_parser

RUN_DIR = Path("/tmp/does-not-matter")


def _argv(adapter, model, effort):
    return adapter.build_argv(
        "exe", RUN_DIR, model, effort, context="", prompt="hi", system_prompt="sp"
    )


def test_claude_omits_effort_flag_when_absent():
    assert "--effort" not in _argv(ClaudeAdapter(), "opus", "")
    argv = _argv(ClaudeAdapter(), "opus", "high")
    i = argv.index("--effort")
    assert argv[i + 1] == "high"


def test_codex_omits_reasoning_when_absent():
    joined = " ".join(_argv(CodexAdapter(), "gpt-5.5", ""))
    assert "model_reasoning_effort" not in joined
    assert "model_reasoning_effort=high" in _argv(CodexAdapter(), "gpt-5.5", "high")


def test_cursor_uses_model_verbatim_when_no_effort():
    # a full id from --list-models is passed through unchanged (no doubling)
    argv = _argv(CursorAdapter(), "gpt-5.3-codex-high", "")
    assert "gpt-5.3-codex-high" in argv
    assert "gpt-5.3-codex-high-" not in " ".join(argv)
    # a base id plus an effort is appended
    argv2 = _argv(CursorAdapter(), "gpt-5.3-codex", "high")
    assert "gpt-5.3-codex-high" in argv2


def test_run_effort_is_optional_in_cli():
    args = build_parser().parse_args(["run", "--client", "fake", "--model", "m", "--prompt", "p"])
    assert args.effort == ""
