# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Passthrough client arguments (`--client-arg`).

Extra raw args appended verbatim to the client launch. (The keying — that args
enter the key only by fingerprint — is covered by tests/test_checksum.py and the
identity tests; here we cover the adapter argv placement and the CLI flag.)
"""

from __future__ import annotations

from pathlib import Path

from generic_ml_cache_core.adapter.out.client.claude import ClaudeAdapter
from generic_ml_cache_core.adapter.out.client.codex import CodexAdapter
from generic_ml_cache_core.adapter.out.client.cursor import CursorAdapter
from generic_ml_cache_cli.cli import main

_ARGS = ["--reasoning", "max", "--flag"]


def _argv(adapter, client_args):
    return adapter.build_argv(
        adapter.default_executable,
        Path("/tmp"),
        "model",
        "high",
        "ctx",
        "PROMPT",
        "sys",
        client_args,
    )


def test_claude_appends_args_verbatim():
    argv = _argv(ClaudeAdapter(), _ARGS)
    # Claude's prompt is on stdin, so the args sit at the very end, in order.
    assert argv[-3:] == _ARGS


def test_codex_places_args_before_the_stdin_marker():
    argv = _argv(CodexAdapter(), _ARGS)
    assert "-" in argv and all(a in argv for a in _ARGS)
    assert max(argv.index(a) for a in _ARGS) < argv.index("-")


def test_cursor_places_args_before_the_prompt_positional():
    argv = _argv(CursorAdapter(), _ARGS)
    assert argv[-1] != _ARGS[-1]
    assert max(argv.index(a) for a in _ARGS) < len(argv) - 1


def test_empty_passthrough_leaves_the_command_line_unchanged():
    for adapter in (ClaudeAdapter(), CodexAdapter(), CursorAdapter()):
        assert _argv(adapter, []) == _argv(adapter, [])
        if isinstance(adapter, CursorAdapter):
            assert _argv(adapter, [])[-1] == "sys\n\nctx\n\nPROMPT"


_CLI = ["--client", "fake", "--model", "m", "--effort", "high"]
_ARGS_CLI = ["--client-arg=--foo", "--client-arg=bar"]


def test_client_arg_keys_run_and_check_identically(capsys):
    assert main(["run", *_CLI, "--prompt", "STDOUT p", *_ARGS_CLI]) == 0
    capsys.readouterr()
    assert main(["check", *_CLI, "--prompt", "STDOUT p", *_ARGS_CLI]) == 0
    assert "status  : hit" in capsys.readouterr().out


def test_passthrough_args_yield_a_distinct_call(capsys):
    assert main(["run", *_CLI, "--prompt", "STDOUT q", "--client-arg=--foo"]) == 0
    capsys.readouterr()
    assert main(["check", *_CLI, "--prompt", "STDOUT q"]) == 0
    assert "status  : miss" in capsys.readouterr().out
