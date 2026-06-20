# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Passthrough client arguments (`--client-arg`).

Extra raw args appended verbatim to the client launch. They are part of the key
(different args = different call = own cassette), but only their *fingerprint* is
keyed, so the raw strings -- which may hold secrets -- never reach a cassette.
"""

from __future__ import annotations

from generic_ml_cache.cache import Request
from generic_ml_cache.common.checksum import checksum_input_data


def _req(**kw) -> Request:
    return Request(client="fake", model="m", effort="high", context="", prompt="p", **kw)


def _key(request: Request) -> str:
    return checksum_input_data(request.input_data)


def test_empty_passthrough_keys_identically_to_none():
    # Back-compat: no args, or an empty list, must key exactly as before.
    assert _req().input_data == _req(client_args=[]).input_data
    assert _key(_req()) == _key(_req(client_args=[]))


def test_passthrough_args_change_the_key():
    assert _key(_req()) != _key(_req(client_args=["--thinking", "high"]))


def test_same_args_in_same_order_share_a_key():
    assert _key(_req(client_args=["--a", "1"])) == _key(_req(client_args=["--a", "1"]))


def test_arg_order_is_significant():
    # CLI flags are positional, so a different order is a different invocation.
    assert _key(_req(client_args=["--a", "--b"])) != _key(_req(client_args=["--b", "--a"]))


def test_raw_args_never_appear_in_the_keyed_data():
    secret = "--token=SUPERSECRET"
    data = _req(client_args=[secret]).input_data

    # The raw secret appears nowhere -- not as a value, not inside a key.
    assert secret not in data.values()
    assert all(secret not in k for k in data)

    # Only a single fingerprint entry, whose key suffix and value are the digest.
    arg_keys = [k for k in data if k.startswith("client_args:")]
    assert len(arg_keys) == 1
    digest = arg_keys[0].split(":", 1)[1]
    assert len(digest) == 64
    assert data[arg_keys[0]] == digest
    assert "SUPERSECRET" not in digest


# --- launch placement: args go in just before each client's prompt -----------

from pathlib import Path  # noqa: E402

from generic_ml_cache.adapters.claude import ClaudeAdapter  # noqa: E402
from generic_ml_cache.adapters.codex import CodexAdapter  # noqa: E402
from generic_ml_cache.adapters.cursor import CursorAdapter  # noqa: E402

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
    # every passthrough arg comes before the trailing "-" (else codex eats them)
    assert max(argv.index(a) for a in _ARGS) < argv.index("-")


def test_cursor_places_args_before_the_prompt_positional():
    argv = _argv(CursorAdapter(), _ARGS)
    # the prompt is the last (variadic) positional; args must precede it
    assert argv[-1] != _ARGS[-1]
    assert max(argv.index(a) for a in _ARGS) < len(argv) - 1


def test_empty_passthrough_leaves_the_command_line_unchanged():
    for adapter in (ClaudeAdapter(), CodexAdapter(), CursorAdapter()):
        assert _argv(adapter, []) == _argv(adapter, [])
        # cursor's prompt stays the trailing positional with no args
        if isinstance(adapter, CursorAdapter):
            assert _argv(adapter, [])[-1] == "sys\n\nctx\n\nPROMPT"


# --- the --client-arg flag flows into the key on both run and check ----------

from generic_ml_cache.cli import main  # noqa: E402

_CLI = ["--client", "fake", "--model", "m", "--effort", "high"]
# Dash-led values use the =form (--client-arg=--foo), as argparse requires.
_ARGS_CLI = ["--client-arg=--foo", "--client-arg=bar"]


def test_client_arg_keys_run_and_check_identically(capsys):
    assert main(["run", *_CLI, "--prompt", "STDOUT p", *_ARGS_CLI]) == 0
    capsys.readouterr()
    assert main(["check", *_CLI, "--prompt", "STDOUT p", *_ARGS_CLI]) == 0
    assert "status  : hit" in capsys.readouterr().out


def test_passthrough_args_yield_a_distinct_cassette(capsys):
    assert main(["run", *_CLI, "--prompt", "STDOUT q", "--client-arg=--foo"]) == 0
    capsys.readouterr()
    # same prompt, no passthrough -> different key -> miss
    assert main(["check", *_CLI, "--prompt", "STDOUT q"]) == 0
    assert "status  : miss" in capsys.readouterr().out
    # same prompt, different passthrough -> also a miss
    capsys.readouterr()
    assert main(["check", *_CLI, "--prompt", "STDOUT q", "--client-arg=--other"]) == 0
    assert "status  : miss" in capsys.readouterr().out
