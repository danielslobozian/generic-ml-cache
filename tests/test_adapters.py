# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys

import pytest

from generic_ml_cache import UnknownClient, get_adapter
from generic_ml_cache.adapters.registry import registered_names
from generic_ml_cache.errors import ClientNotFound
from generic_ml_cache.prime_directive import PRIME_DIRECTIVE


def test_builtins_are_registered():
    for name in ("claude", "codex", "cursor"):
        assert name in registered_names()


def test_unknown_client_raises():
    with pytest.raises(UnknownClient):
        get_adapter("does-not-exist")


@pytest.mark.parametrize("client", ["claude", "codex", "cursor"])
def test_build_argv_includes_model_and_inputs(client, tmp_path):
    adapter = get_adapter(client)
    argv = adapter.build_argv(
        executable="/usr/bin/" + client,
        run_dir=tmp_path,
        model="m-x",
        effort="high",
        context="CTX",
        prompt="PROMPT",
        system_prompt=PRIME_DIRECTIVE,
    )
    assert argv[0].endswith(client)
    joined = " ".join(argv)
    assert "m-x" in joined  # the model id appears somewhere
    # The prompt is delivered to the client either on stdin (claude/codex) or as a
    # positional argument (cursor) -- exactly one channel carries it.
    payload = adapter.stdin_payload("CTX", "PROMPT", PRIME_DIRECTIVE) or ""
    assert ("PROMPT" in joined) ^ ("PROMPT" in payload)
    # effort surfaces somehow (a flag value, a config kv, or baked into model id)
    assert any("high" in a for a in argv)


def test_resolve_executable_honors_explicit_path(tmp_path):
    adapter = get_adapter("claude")
    fake = tmp_path / "claude-bin"
    fake.write_text("#!/bin/sh\n", encoding="utf-8")
    assert adapter.resolve_executable(str(fake)) == str(fake)


def test_resolve_executable_missing_path_raises():
    adapter = get_adapter("claude")
    with pytest.raises(ClientNotFound):
        adapter.resolve_executable("/no/such/dir/claude")


def test_resolve_executable_found_on_path():
    adapter = get_adapter("claude")
    # Pass a bare name (no separator) that exists on PATH -> exercises the
    # shutil.which branch without mutating the shared adapter.
    name = "python" if sys.platform == "win32" else "sh"
    path = adapter.resolve_executable(name)
    assert path


def test_unknown_executable_name_raises():
    adapter = get_adapter("claude")  # default_executable "claude" not installed
    with pytest.raises(ClientNotFound):
        adapter.resolve_executable("definitely-not-a-real-binary-xyz")


# --- write/trust door (v0.0.6 record-path fix) -----------------------------

EXPECTED_WRITE_GRANT = {
    "claude": ["--permission-mode", "acceptEdits"],
    "codex": ["--skip-git-repo-check", "--sandbox", "workspace-write"],
    "cursor": ["--trust"],
}


@pytest.mark.parametrize("client", ["claude", "codex", "cursor"])
def test_write_access_argv_opens_write_door(client, tmp_path):
    grant = get_adapter(client).write_access_argv(tmp_path)
    for token in EXPECTED_WRITE_GRANT[client]:
        assert token in grant


@pytest.mark.parametrize("client", ["claude", "codex", "cursor"])
def test_build_argv_includes_write_grant(client, tmp_path):
    argv = get_adapter(client).build_argv(
        executable="/usr/bin/" + client,
        run_dir=tmp_path,
        model="m-x",
        effort="",
        context="CTX",
        prompt="PROMPT",
        system_prompt=PRIME_DIRECTIVE,
    )
    for token in EXPECTED_WRITE_GRANT[client]:
        assert token in argv


def test_write_grant_precedes_stdin_placeholder_codex(tmp_path):
    # codex exec reads the prompt from stdin via a trailing "-" placeholder; the
    # write flags must sit before it or the CLI parser rejects flags after the
    # positional. (cursor no longer has any trailing positional -- prompt on stdin.)
    argv = get_adapter("codex").build_argv(
        executable="/usr/bin/codex",
        run_dir=tmp_path,
        model="m-x",
        effort="",
        context="",
        prompt="PROMPT",
        system_prompt=PRIME_DIRECTIVE,
    )
    assert argv[-1] == "-"  # stdin placeholder is the trailing positional
    assert argv.index(EXPECTED_WRITE_GRANT["codex"][0]) < len(argv) - 1


def test_codex_write_grant_pins_run_dir_as_fence(tmp_path):
    grant = get_adapter("codex").write_access_argv(tmp_path)
    assert "-C" in grant
    assert str(tmp_path) in grant


def test_base_write_access_argv_defaults_empty(tmp_path):
    # The fake adapter does not override the seam, so the base default applies.
    assert get_adapter("fake").write_access_argv(tmp_path) == []


# --- cursor delivers the directive via the prompt (no system-prompt flag) ----


def test_cursor_has_no_system_prompt_flag(tmp_path):
    # Current cursor-agent removed --system-prompt; the adapter must not emit it.
    argv = get_adapter("cursor").build_argv(
        executable="/usr/bin/cursor-agent",
        run_dir=tmp_path,
        model="m-x",
        effort="",
        context="CTX",
        prompt="PROMPT",
        system_prompt=PRIME_DIRECTIVE,
    )
    assert "--system-prompt" not in argv


def test_cursor_directive_is_folded_into_the_prompt(tmp_path):
    # No system-prompt channel and no stdin path -> the directive rides in the
    # positional prompt argument (delivery-level only; the Request/key are
    # untouched, tested via cache keying).
    adapter = get_adapter("cursor")
    argv = adapter.build_argv(
        executable="/usr/bin/cursor-agent",
        run_dir=tmp_path,
        model="m-x",
        effort="",
        context="CTX",
        prompt="PROMPT",
        system_prompt=PRIME_DIRECTIVE,
    )
    full_prompt = argv[-1]  # the trailing positional prompt
    assert PRIME_DIRECTIVE in full_prompt
    assert "CTX" in full_prompt
    assert "PROMPT" in full_prompt
    assert adapter.stdin_payload("CTX", "PROMPT", PRIME_DIRECTIVE) is None


def _argv(adapter, tmp_path, grants=()):
    return adapter.build_argv(
        executable="/usr/bin/x",
        run_dir=tmp_path,
        model="m",
        effort="",
        context="",
        prompt="P",
        system_prompt=PRIME_DIRECTIVE,
        client_args=(),
        grants=grants,
    )


@pytest.mark.parametrize("client", ["claude", "codex", "cursor"])
def test_no_grant_emits_no_network_door(client, tmp_path):
    # Without a net grant, no adapter opens any network flag (default behaviour
    # is unchanged): the grant is purely additive.
    joined = " ".join(_argv(get_adapter(client), tmp_path))
    assert "network_access" not in joined
    assert "WebFetch" not in joined and "WebSearch" not in joined


def test_net_grant_opens_codex_network(tmp_path):
    # Codex's net door is the one process-level toggle: granting net flips
    # network_access on inside the workspace-write sandbox.
    joined = " ".join(_argv(get_adapter("codex"), tmp_path, grants=("net",)))
    assert "sandbox_workspace_write.network_access=true" in joined


def test_net_grant_opens_claude_network(tmp_path):
    # Claude's reliable net door bypasses the permission wall (the narrow tool-allow
    # is flaky) and replaces the acceptEdits write door for a net call.
    with_net = _argv(get_adapter("claude"), tmp_path, grants=("net",))
    assert "--dangerously-skip-permissions" in with_net
    assert "acceptEdits" not in " ".join(with_net)  # net posture replaces the write door
    # ...and the bypass is absent without the grant
    assert "--dangerously-skip-permissions" not in _argv(get_adapter("claude"), tmp_path)


def test_net_grant_keeps_cursor_prompt_trailing(tmp_path):
    # cursor-agent reads the prompt as the trailing positional; a grant must never
    # land after it (or it would be read as prompt text).
    argv = _argv(get_adapter("cursor"), tmp_path, grants=("net",))
    assert argv[-1].endswith("P")
    assert "--model" in argv
    assert "--force" in argv  # the verified cursor net door
    # ...and --force is not present without the grant
    assert "--force" not in _argv(get_adapter("cursor"), tmp_path)
