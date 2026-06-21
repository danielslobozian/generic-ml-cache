# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

import pytest

from generic_ml_cache import config
from generic_ml_cache.cli import main
from generic_ml_cache.common.errors import ConfigError


def _write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_yields_empty_defaults(tmp_path):
    cfg = config.load(tmp_path / "absent.ini")
    assert cfg.source is None
    assert cfg.mode is None and cfg.store is None and cfg.timeout is None


def test_load_reads_defaults_section(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nmode = refresh\nstore = boxes\ntimeout = 90\n")
    cfg = config.load(p)
    assert cfg.source == p
    assert cfg.mode == "refresh"
    assert cfg.store == "boxes"
    assert cfg.timeout == 90.0


def test_invalid_mode_in_file_raises(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nmode = sideways\n")
    with pytest.raises(ConfigError):
        config.load(p)


def test_invalid_timeout_in_file_raises(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\ntimeout = soon\n")
    with pytest.raises(ConfigError):
        config.load(p)


def test_precedence_default_then_config_then_env_then_flag(tmp_path, monkeypatch):
    # config file sets refresh ...
    p = _write(tmp_path / "c.ini", "[defaults]\nmode = refresh\n")
    cfg = config.load(p)
    assert config.resolve_settings(cfg)["mode"] == ("refresh", "config")
    # ... env overrides the file ...
    monkeypatch.setenv("GMLCACHE_MODE", "offline")
    assert config.resolve_settings(cfg)["mode"] == ("offline", "env")
    # ... and an explicit flag overrides env.
    assert config.resolve_settings(cfg, mode_flag="cache")["mode"] == ("cache", "flag")


def test_default_when_nothing_set(tmp_path):
    settings = config.resolve_settings(config.load(tmp_path / "absent.ini"))
    assert settings["mode"] == ("cache", "default")
    assert settings["store"] == (str(config.default_store_path()), "default")
    assert settings["timeout"] == (None, "default")


def test_invalid_env_mode_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("GMLCACHE_MODE", "turbo")
    with pytest.raises(ConfigError):
        config.resolve_settings(config.load(tmp_path / "absent.ini"))


def test_status_cli_reports_source_and_settings(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[defaults]\nmode = offline\nstore = vault\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["loaded"] is True
    assert payload["config_file"] == str(p)
    assert payload["settings"]["mode"] == {"value": "offline", "source": "config"}
    assert payload["settings"]["store"] == {"value": "vault", "source": "config"}


def test_status_cli_when_no_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "absent.ini"))
    rc = main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "not present" in out
    assert "from default" in out


def test_missing_file_yields_empty_executables(tmp_path):
    cfg = config.load(tmp_path / "absent.ini")
    assert cfg.executables == {}


def test_load_reads_executables_section(tmp_path):
    p = _write(
        tmp_path / "c.ini",
        "[executables]\nclaude = /opt/claude/bin/claude\ncodex = /usr/local/bin/codex\n",
    )
    cfg = config.load(p)
    assert cfg.executables == {
        "claude": "/opt/claude/bin/claude",
        "codex": "/usr/local/bin/codex",
    }


def test_unknown_executable_key_is_kept_not_rejected(tmp_path):
    # client names are an extensible registry, so an unknown key is not an error.
    p = _write(tmp_path / "c.ini", "[executables]\nnot-a-real-client = /some/where\n")
    cfg = config.load(p)
    assert cfg.executables == {"not-a-real-client": "/some/where"}


def test_executable_for_precedence(tmp_path):
    cfg = config.load(_write(tmp_path / "c.ini", "[executables]\nclaude = /from/config\n"))
    # flag wins
    assert config.executable_for(cfg, "claude", flag="/from/flag") == "/from/flag"
    # else config
    assert config.executable_for(cfg, "claude") == "/from/config"
    # else None (adapter falls back to its own PATH lookup)
    assert config.executable_for(cfg, "codex") is None


def test_status_json_includes_executables(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[executables]\nclaude = /opt/claude\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["executables"] == {"claude": "/opt/claude"}


def test_status_text_shows_executables(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[executables]\nclaude = /opt/claude\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "claude" in out and "/opt/claude" in out


def test_doctor_cli_honors_configured_executable(tmp_path, monkeypatch, capsys):
    # point the fake client at an absent binary via config -> doctor reports it missing
    p = _write(tmp_path / "c.ini", "[executables]\nfake = definitely-not-a-real-binary-xyz123\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fake" in out and "missing" in out


# --- store ownership + init (0.0.7) ----------------------------------------


def test_store_default_is_under_the_per_user_data_dir(tmp_path):
    # the autouse fixture isolates the data dir into tmp (XDG_DATA_HOME on posix,
    # LOCALAPPDATA on Windows); the store default is <data dir>/store there.
    expected = config.default_data_dir() / "store"
    assert config.default_store_path() == expected
    assert expected.is_relative_to(tmp_path)  # isolated, never the real machine
    settings = config.resolve_settings(config.load(tmp_path / "absent.ini"))
    assert settings["store"] == (str(expected), "default")


def test_store_from_config_wins_over_default(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text(f"[defaults]\nstore = {tmp_path / 'mystore'}\n")
    settings = config.resolve_settings(config.load(p))
    assert settings["store"] == (str(tmp_path / "mystore"), "config")


def test_store_has_no_env_override(tmp_path, monkeypatch):
    # GMLCACHE_STORE is retired: setting it must not change the resolved store
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path / "ignored"))
    settings = config.resolve_settings(config.load(tmp_path / "absent.ini"))
    assert settings["store"] == (str(config.default_store_path()), "default")


def test_init_writes_config_and_is_idempotent(tmp_path):
    target = tmp_path / "cfg" / "config.ini"
    path, created = config.write_default_config(target)
    assert created is True and path == target and target.is_file()
    # the written file parses and pins the store at the resolved default
    assert config.load(target).store == str(config.default_store_path())
    # a second call never overwrites
    again_path, again_created = config.write_default_config(target)
    assert again_path == target and again_created is False
