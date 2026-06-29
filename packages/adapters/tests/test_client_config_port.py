# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ClientConfigPort descriptors — the pure config knowledge each
client exposes (the grant file, the credential files, the config-home env var).

These are what core consumes to prepare a managed run's config home; core does
the writing. The descriptors here carry no filesystem side effects of their own.
"""

from __future__ import annotations

from pathlib import Path

from generic_ml_cache_core.adapter.registry import get_adapter
from generic_ml_cache_core.application.port.out.client_config_port import ClientConfigPort


def test_real_adapters_are_client_config_ports():
    for name in ("claude", "codex", "cursor"):
        assert isinstance(get_adapter(name), ClientConfigPort)


def test_config_home_env_var_per_client():
    assert get_adapter("claude").config_home_env_var() == "CLAUDE_CONFIG_DIR"
    assert get_adapter("codex").config_home_env_var() == "CODEX_HOME"
    assert get_adapter("cursor").config_home_env_var() == "CURSOR_CONFIG_DIR"


def test_grant_config_file_name_and_write_always_on():
    claude = get_adapter("claude").build_grants_config_file(())
    assert claude.file_name == "settings.json"
    assert b"Write(**)" in claude.content  # write is always on (record-path guarantee)

    codex = get_adapter("codex").build_grants_config_file(())
    assert codex.file_name == "config.toml"
    assert b"workspace-write" in codex.content

    cursor = get_adapter("cursor").build_grants_config_file(())
    assert cursor.file_name == "cli-config.json"
    assert b"Write(**)" in cursor.content


def test_net_grant_appears_in_each_descriptor():
    assert b"WebFetch" in get_adapter("claude").build_grants_config_file(("net",)).content
    assert (
        b"network_access = true" in get_adapter("codex").build_grants_config_file(("net",)).content
    )
    assert b"Shell(**)" in get_adapter("cursor").build_grants_config_file(("net",)).content


def test_claude_token_files_include_main_config_and_dir_children(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / ".claude").mkdir(parents=True)
    (fake_home / ".claude" / ".credentials.json").write_text("{}", encoding="utf-8")
    (fake_home / ".claude" / "projects").mkdir()  # a skipped bulk-cache child
    (fake_home / ".claude.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    targets = {c.target_name for c in get_adapter("claude").get_token_files()}
    assert ".credentials.json" in targets  # real cred seeded
    assert ".claude.json" in targets  # top-level main config seeded
    assert "projects" not in targets  # bulk-cache child skipped


def test_codex_token_files_present_only_when_auth_exists(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    assert get_adapter("codex").get_token_files() == []  # no ~/.codex/auth.json yet

    (fake_home / ".codex").mkdir(parents=True)
    (fake_home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
    creds = get_adapter("codex").get_token_files()
    assert [c.target_name for c in creds] == ["auth.json"]


def test_cursor_seeds_no_credentials():
    assert get_adapter("cursor").get_token_files() == []
