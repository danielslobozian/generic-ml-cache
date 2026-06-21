# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys

import pytest

from generic_ml_cache import UnknownClient, get_adapter
from generic_ml_cache.adapter.out.client.registry import registered_names
from generic_ml_cache.common.errors import ClientNotFound
from generic_ml_cache.adapter.out.client.prime_directive import PRIME_DIRECTIVE


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
    name = "python" if sys.platform == "win32" else "sh"
    assert adapter.resolve_executable(name)


def test_unknown_executable_name_raises():
    adapter = get_adapter("claude")
    with pytest.raises(ClientNotFound):
        adapter.resolve_executable("definitely-not-a-real-binary-xyz")


# --- cursor delivers the directive via the prompt (no system-prompt flag) ----


def test_cursor_has_no_system_prompt_flag(tmp_path):
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


# --- transport stays in argv; capability doors moved to the config file ------

# Flags each adapter still needs in argv just to run head-less and write into its
# own run folder. Capability gating (read/write/shell/net/web-search) is NOT in
# argv any more -- it lives in the config file rendered by grant_setup.
_TRANSPORT = {
    "claude": [],  # acceptEdits moved into settings.json defaultMode
    "codex": ["--skip-git-repo-check"],  # plus -C <run_dir>, checked separately
    "cursor": ["--trust"],  # workspace-trust acceptance (transport, not a capability)
}


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
def test_build_argv_carries_transport_not_capability_flags(client, tmp_path):
    argv = _argv(get_adapter(client), tmp_path)
    joined = " ".join(argv)
    for token in _TRANSPORT[client]:
        assert token in argv
    # No capability door may leak into argv any more -- they live in the file.
    for leak in (
        "acceptEdits",
        "--settings",
        "--sandbox",
        "network_access",
        "WebFetch",
        "WebSearch",
        "--force",
        "--dangerously-skip-permissions",
    ):
        assert leak not in joined


def test_codex_pins_run_dir_as_write_fence(tmp_path):
    argv = _argv(get_adapter("codex"), tmp_path)
    assert "-C" in argv
    assert str(tmp_path) in argv
    assert argv[-1] == "-"  # stdin placeholder stays the trailing positional


# --- the uniform grant door: a config FILE in a redirected home --------------


def _grant(client, tmp_path, grants):
    adapter = get_adapter(client)
    home = tmp_path / "home"
    env = adapter.grant_setup(tmp_path / "run", home, grants)
    return adapter, home, env


def test_grant_setup_redirects_each_clients_home(tmp_path):
    cases = {
        "claude": ("CLAUDE_CONFIG_DIR", "settings.json"),
        "codex": ("CODEX_HOME", "config.toml"),
        "cursor": ("CURSOR_CONFIG_DIR", "cli-config.json"),
    }
    for client, (var, fname) in cases.items():
        _, home, env = _grant(client, tmp_path / client, ())
        assert env.get(var) == str(home)
        assert (home / fname).is_file()


def test_write_is_always_on_in_the_file(tmp_path):
    # The record-path guarantee: a file-producing call must write even with no
    # grants. Each client's default file opens its own run-folder write.
    _, home, _ = _grant("claude", tmp_path / "c", ())
    assert "Write(**)" in (home / "settings.json").read_text()
    _, home, _ = _grant("codex", tmp_path / "x", ())
    assert "workspace-write" in (home / "config.toml").read_text()
    _, home, _ = _grant("cursor", tmp_path / "u", ())
    assert "Write(**)" in (home / "cli-config.json").read_text()


def test_net_grant_opens_each_client_in_the_file(tmp_path):
    _, home, _ = _grant("claude", tmp_path / "c", ("net",))
    assert "WebFetch" in (home / "settings.json").read_text()
    _, home, _ = _grant("codex", tmp_path / "x", ("net",))
    assert "network_access = true" in (home / "config.toml").read_text()
    # cursor: shell allowed in the file; external egress forced via grant_argv.
    adapter, home, _ = _grant("cursor", tmp_path / "u", ("net",))
    assert "Shell(**)" in (home / "cli-config.json").read_text()
    assert adapter.grant_argv(("net",)) == ["--force"]


def test_web_search_grant_in_the_file(tmp_path):
    _, home, _ = _grant("claude", tmp_path / "c", ("web-search",))
    assert "WebSearch" in (home / "settings.json").read_text()
    _, home, _ = _grant("codex", tmp_path / "x", ("web-search",))
    assert 'web_search = "live"' in (home / "config.toml").read_text()


def test_read_and_shell_grants_open_in_the_file(tmp_path):
    _, home, _ = _grant("claude", tmp_path / "c", ("read", "shell"))
    text = (home / "settings.json").read_text()
    assert "Read(**)" in text and "Bash(**)" in text
    _, home, _ = _grant("cursor", tmp_path / "u", ("read", "shell"))
    text = (home / "cli-config.json").read_text()
    assert "Read(**)" in text and "Shell(**)" in text


def test_no_grant_opens_no_capability_in_the_file(tmp_path):
    # Additive: without grants, nothing beyond the always-on write appears.
    _, home, _ = _grant("claude", tmp_path / "c", ())
    text = (home / "settings.json").read_text()
    assert "WebFetch" not in text and "WebSearch" not in text and "Bash(**)" not in text
    _, home, _ = _grant("codex", tmp_path / "x", ())
    assert "network_access" not in (home / "config.toml").read_text()
    assert get_adapter("cursor").grant_argv(()) == []


def test_base_grant_setup_defaults_empty(tmp_path):
    # The fake adapter does not override the seam -> base default: no env, no file.
    assert get_adapter("fake").grant_setup(tmp_path, tmp_path / "h", ("net",)) == {}


def test_claude_grant_setup_seeds_main_config_and_dir(tmp_path, monkeypatch):
    # Claude Code needs both the top-level .claude.json AND the ~/.claude dir creds
    # seeded into the redirected home, or it warns the main config is missing.
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    (fake_home / ".claude" / ".credentials.json").write_text("{}", encoding="utf-8")
    (fake_home / ".claude.json").write_text('{"x":1}', encoding="utf-8")
    from pathlib import Path as _P

    monkeypatch.setattr(_P, "home", staticmethod(lambda: fake_home))
    cfg = tmp_path / "cfg"
    get_adapter("claude").grant_setup(tmp_path / "run", cfg, ())
    assert (cfg / ".claude.json").read_text() == '{"x":1}'  # main config seeded
    assert (cfg / ".credentials.json").is_file()  # dir creds seeded
    assert (cfg / "settings.json").is_file()  # our grant file written
