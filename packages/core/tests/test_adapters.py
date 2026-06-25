# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from generic_ml_cache_core import UnknownClient, get_adapter
from generic_ml_cache_core.adapter.out.client.registry import registered_names
from generic_ml_cache_core.common.errors import ClientNotFound
from generic_ml_cache_core.adapter.out.client.prime_directive import (
    PRIME_DIRECTIVE,
    build_system_prompt,
)


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


def test_claude_grant_setup_copies_subdirectory_from_claude_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    extensions_dir = fake_home / ".claude" / "extensions"
    extensions_dir.mkdir(parents=True)
    (extensions_dir / "config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    cfg = tmp_path / "cfg"
    get_adapter("claude").grant_setup(tmp_path / "run", cfg, ())
    assert (cfg / "extensions" / "config.json").is_file()


def test_claude_grant_setup_survives_main_config_copy_error(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir(parents=True)
    (fake_home / ".claude.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    original_copy = shutil.copy2

    def _raise_on_claude_json(src, dst, **kwargs):
        if str(dst).endswith(".claude.json"):
            raise OSError("permission denied")
        return original_copy(src, dst, **kwargs)

    monkeypatch.setattr(shutil, "copy2", _raise_on_claude_json)
    cfg = tmp_path / "cfg"
    get_adapter("claude").grant_setup(tmp_path / "run", cfg, ())
    assert (cfg / "settings.json").is_file()
    assert not (cfg / ".claude.json").is_file()


def test_codex_grant_setup_survives_auth_copy_error(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".codex").mkdir(parents=True)
    (fake_home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    def _always_raise_oserror(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(shutil, "copy2", _always_raise_oserror)
    cfg = tmp_path / "cfg"
    result = get_adapter("codex").grant_setup(tmp_path / "run", cfg, ())
    assert "CODEX_HOME" in result
    assert (cfg / "config.toml").is_file()
    assert not (cfg / "auth.json").is_file()


def test_claude_grant_setup_survives_credential_copy_error_in_claude_dir(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    (fake_home / ".claude" / ".credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    def _always_raise_oserror(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(shutil, "copy2", _always_raise_oserror)
    cfg = tmp_path / "cfg"
    get_adapter("claude").grant_setup(tmp_path / "run", cfg, ())
    assert (cfg / "settings.json").is_file()
    assert not (cfg / ".credentials.json").is_file()


# --- read_access_argv ---------------------------------------------------------


def test_claude_read_access_argv_produces_add_dir_flag_for_each_path():
    extra_paths = ["/data/dir-a", "/data/dir-b"]
    argv = get_adapter("claude").read_access_argv(extra_paths)
    assert argv == ["--add-dir", "/data/dir-a", "--add-dir", "/data/dir-b"]


def test_claude_read_access_argv_returns_empty_list_for_no_paths():
    assert get_adapter("claude").read_access_argv([]) == []


# --- stream_event: pure parsing, no subprocess --------------------------------


@pytest.mark.parametrize(
    "raw_line, expected_result",
    [
        ("not json", None),
        ('"a string"', None),
        ('{"type": "system", "subtype": "init"}', {"kind": "start"}),
        ('{"type": "system", "subtype": "thinking_tokens"}', {"kind": "thinking"}),
        ('{"type": "system", "subtype": "other"}', None),
        (
            '{"type": "stream_event", "event": {"type": "content_block_start",'
            ' "content_block": {"type": "tool_use", "name": "bash"}}}',
            {"kind": "tool", "name": "bash"},
        ),
        ('{"type": "stream_event", "event": {"type": "other"}}', None),
        ('{"type": "result"}', {"kind": "result"}),
        ('{"type": "unknown"}', None),
    ],
)
def test_claude_stream_event_parses_correctly(raw_line, expected_result):
    assert get_adapter("claude").stream_event(raw_line) == expected_result


@pytest.mark.parametrize(
    "raw_line, expected_result",
    [
        ("not json", None),
        ('"a string"', None),
        ('{"type": "thread.started"}', {"kind": "start"}),
        ('{"type": "turn.completed"}', {"kind": "result"}),
        ('{"type": "error"}', {"kind": "error"}),
        ('{"type": "turn.failed"}', {"kind": "error"}),
        (
            '{"type": "item.completed", "item": {"type": "agent_message"}}',
            {"kind": "message"},
        ),
        (
            '{"type": "item.completed", "item": {"type": "code_cell"}}',
            {"kind": "tool", "name": "code_cell"},
        ),
        ('{"type": "item.completed", "item": {}}', None),
        ('{"type": "other"}', None),
    ],
)
def test_codex_stream_event_parses_correctly(raw_line, expected_result):
    assert get_adapter("codex").stream_event(raw_line) == expected_result


@pytest.mark.parametrize(
    "raw_line, expected_result",
    [
        ("not json", None),
        ('"a string"', None),
        ('{"type": "system", "subtype": "init"}', {"kind": "start"}),
        ('{"type": "assistant"}', {"kind": "message"}),
        ('{"type": "result"}', {"kind": "result"}),
        ('{"type": "unknown"}', None),
    ],
)
def test_cursor_stream_event_parses_correctly(raw_line, expected_result):
    assert get_adapter("cursor").stream_event(raw_line) == expected_result


# --- parse_output edge cases --------------------------------------------------


def test_codex_parse_output_tolerates_empty_and_non_json_lines_in_stream():
    stdout = "\n".join(
        [
            "",  # empty line — exercises the "not line: continue" guard
            "garbage line",
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "hello"}}',
            '{"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}',
        ]
    )
    parsed_output = get_adapter("codex").parse_output(stdout)
    assert parsed_output.text.strip() == "hello"


def test_codex_parse_output_tolerates_non_dict_json_in_stream():
    stdout = "\n".join(
        [
            '"just a string"',
            '{"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}',
            '{"type": "turn.completed", "usage": {}}',
        ]
    )
    parsed_output = get_adapter("codex").parse_output(stdout)
    assert parsed_output.text.strip() == "hi"


def test_cursor_parse_output_falls_back_to_raw_when_result_is_not_a_string():
    raw_stdout = '{"result": 42, "usage": {}}'
    parsed_output = get_adapter("cursor").parse_output(raw_stdout)
    assert parsed_output.text == raw_stdout
    assert parsed_output.usage is None


# --- models_argv --------------------------------------------------------------


def test_cursor_models_argv_returns_list_models_command():
    argv = get_adapter("cursor").models_argv("/usr/bin/cursor-agent")
    assert argv == ["/usr/bin/cursor-agent", "--list-models"]


def test_cursor_parse_model_list_marks_default_model():
    stdout = "claude-4-5 - Claude 4.5 (default)\ngpt-5 - GPT-5\n"
    models = get_adapter("cursor").parse_model_list(stdout)
    default_models = [model for model in models if model.default]
    assert len(default_models) == 1
    assert default_models[0].id == "claude-4-5"
    assert default_models[0].name == "Claude 4.5"


def test_cursor_parse_model_list_marks_current_model():
    stdout = "claude-4-5 - Claude 4.5\ngpt-5 - GPT-5 (current)\n"
    models = get_adapter("cursor").parse_model_list(stdout)
    current_models = [model for model in models if model.current]
    assert len(current_models) == 1
    assert current_models[0].id == "gpt-5"
    assert current_models[0].name == "GPT-5"


def test_cursor_parse_model_list_skips_tip_line_containing_separator():
    # "Tip:" lines that also contain " - " must be filtered by the second guard (line 183)
    stdout = "Tip: pass --model to select - a model\nclaude-4-5 - Claude 4.5\n"
    models = get_adapter("cursor").parse_model_list(stdout)
    assert len(models) == 1
    assert models[0].id == "claude-4-5"


def test_cursor_parse_model_list_skips_entry_with_empty_ident():
    # A line whose ident is empty after stripping triggers the ident-guard continue (line 187)
    stdout = " - orphaned label\nclaude-4-5 - Claude 4.5\n"
    models = get_adapter("cursor").parse_model_list(stdout)
    assert len(models) == 1
    assert models[0].id == "claude-4-5"


# --- build_system_prompt: allowed_read_paths branch ---------------------------


def test_build_system_prompt_includes_allowed_read_paths_when_provided():
    allowed_paths = ["/data/input.txt", "/shared/context/"]
    prompt = build_system_prompt(allowed_read_paths=allowed_paths)
    assert "DECLARED READ PATHS" in prompt
    assert "/data/input.txt" in prompt
    assert "/shared/context/" in prompt


def test_build_system_prompt_includes_user_prompt_after_directive():
    user_prompt = "You are a helpful assistant."
    prompt = build_system_prompt(user_system_prompt=user_prompt)
    directive_index = prompt.index("PRIME DIRECTIVE")
    user_index = prompt.index(user_prompt)
    assert directive_index < user_index


def test_build_system_prompt_combines_read_paths_and_user_prompt():
    prompt = build_system_prompt(
        user_system_prompt="Focus on Python.",
        allowed_read_paths=["/src/main.py"],
    )
    assert "DECLARED READ PATHS" in prompt
    assert "/src/main.py" in prompt
    assert "Focus on Python." in prompt
