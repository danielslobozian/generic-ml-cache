# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Prompt + context are delivered to the client on stdin, never as an argv
argument, so a large prompt cannot hit the OS single-argument size limit
(MAX_ARG_STRLEN on Linux, the whole-command-line cap on Windows, ARG_MAX on
macOS). This is delivery-only: the cassette key is unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest

from generic_ml_cache.adapter.out.client.claude import ClaudeAdapter
from generic_ml_cache.adapter.out.client.codex import CodexAdapter
from generic_ml_cache.adapter.out.client.cursor import CursorAdapter
from generic_ml_cache.cli import main

# Larger than the Linux single-argument limit (128 KiB) and the Windows
# whole-command-line limit (~32 KB), so this would break if passed as an argument.
HUGE = "X" * 200_000


@pytest.mark.parametrize("adapter", [ClaudeAdapter(), CodexAdapter()])
def test_prompt_goes_to_stdin_not_argv(adapter):
    argv = adapter.build_argv("exe", Path("/run"), "model", "high", "ctx", HUGE, "sys")
    payload = adapter.stdin_payload("ctx", HUGE, "sys")

    joined = " ".join(argv)
    assert HUGE not in joined  # the big prompt is not an argv argument
    assert len(joined) < 10_000  # argv stays small no matter how large the prompt
    assert payload is not None and HUGE in payload  # it rides on stdin instead


def test_cursor_keeps_prompt_as_argv_positional():
    # cursor-agent has no stdin/file prompt path, so its prompt stays in argv and
    # is therefore bounded by the OS argument-size limit (a documented cursor
    # constraint, not something the cache can work around).
    adapter = CursorAdapter()
    argv = adapter.build_argv("exe", Path("/run"), "model", "high", "ctx", HUGE, "sys")
    assert argv[-1].endswith(HUGE) or HUGE in argv[-1]  # prompt is the trailing arg
    assert adapter.stdin_payload("ctx", HUGE, "sys") is None  # nothing on stdin


def test_command_line_size_guard_is_legible_and_platform_aware():
    # The guard fires only when the assembled command line would exceed THIS OS's
    # real limit, so the test sizes its oversize argument against that limit -- it
    # behaves correctly on Linux (per-arg), Windows and macOS (total).
    from generic_ml_cache.common.errors import CommandLineTooLong
    from generic_ml_cache.adapter.out.client.isolation import (
        _check_command_line_size,
        _command_line_limit,
    )

    # A normal command line passes untouched.
    _check_command_line_size(["exe", "--model", "m", "--print", "a short prompt"])

    # One whose prompt argument exceeds this OS's limit fails with a clear error.
    _, limit, _ = _command_line_limit()
    oversize = "x" * (limit + 8192)
    with pytest.raises(CommandLineTooLong):
        _check_command_line_size(["exe", "--print", oversize])


def test_large_prompt_round_trips_through_stdin(capsys):
    # End-to-end through the launcher's stdin path: record then replay a prompt far
    # larger than any argv limit. "STDOUT done" acts; the filler is one giant
    # unknown directive line and is ignored.
    big = "STDOUT done\n" + HUGE
    common = ["run", "--client", "fake_stdin", "--model", "m1", "--effort", "high", "--prompt", big]

    assert main(common) == 0
    assert "done" in capsys.readouterr().out

    assert main(common + ["--offline"]) == 0  # replay from cache succeeds
    assert "done" in capsys.readouterr().out
