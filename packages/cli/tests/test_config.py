# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

import pytest
from generic_ml_cache_core.common.errors import ConfigError

from generic_ml_cache_cli import config
from generic_ml_cache_cli.cli import main


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
    assert settings["persist"] == ("cache", "default")
    assert settings["store"] == (str(config.default_store_path()), "default")
    assert settings["timeout"] == (None, "default")


def test_invalid_env_mode_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("GMLCACHE_MODE", "turbo")
    with pytest.raises(ConfigError):
        config.resolve_settings(config.load(tmp_path / "absent.ini"))


def test_persist_precedence_default_then_config_then_env_then_flag(tmp_path, monkeypatch):
    # config file sets meter ...
    p = _write(tmp_path / "c.ini", "[defaults]\npersist = meter\n")
    cfg = config.load(p)
    assert config.resolve_settings(cfg)["persist"] == ("meter", "config")
    # ... env overrides the file ...
    monkeypatch.setenv("GMLCACHE_PERSIST", "dataset")
    assert config.resolve_settings(cfg)["persist"] == ("dataset", "env")
    # ... and an explicit flag overrides env.
    assert config.resolve_settings(cfg, persist_flag="cache")["persist"] == ("cache", "flag")


def test_invalid_persist_in_file_raises(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\npersist = hoard\n")
    with pytest.raises(ConfigError):
        config.load(p)


def test_invalid_env_persist_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("GMLCACHE_PERSIST", "hoard")
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


def test_max_age_parsed_from_file(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nmax_age = 30d\n")
    cfg = config.load(p)
    assert cfg.max_age == 30 * 86400


def test_max_age_units(tmp_path):
    for spec, expected in [("1s", 1.0), ("2m", 120.0), ("3h", 10800.0), ("1w", 604800.0)]:
        p = _write(tmp_path / f"c_{spec}.ini", f"[defaults]\nmax_age = {spec}\n")
        assert config.load(p).max_age == expected


def test_max_age_invalid_unit_raises(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nmax_age = 30x\n")
    with pytest.raises(ConfigError):
        config.load(p)


def test_max_age_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("GMLCACHE_MAX_AGE", "7d")
    settings = config.resolve_settings(config.load(tmp_path / "absent.ini"))
    assert settings["max_age"] == (7 * 86400, "env")


def test_max_age_default_is_none(tmp_path):
    settings = config.resolve_settings(config.load(tmp_path / "absent.ini"))
    assert settings["max_age"] == (None, "default")


# --- adapters whitelist (0.16.0) -------------------------------------------


def test_adapters_omitted_yields_none(tmp_path):
    cfg = config.load(tmp_path / "absent.ini")
    assert cfg.adapters is None


def test_adapters_wildcard_yields_none(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = *\n")
    assert config.load(p).adapters is None


def test_adapters_single_name(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = claude\n")
    assert config.load(p).adapters == frozenset({"claude"})


def test_adapters_multiple_names(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = claude, cursor, codex\n")
    assert config.load(p).adapters == frozenset({"claude", "cursor", "codex"})


def test_adapters_names_are_stripped(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters =  claude ,  cursor \n")
    assert config.load(p).adapters == frozenset({"claude", "cursor"})


def test_adapters_empty_string_raises(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = \n")
    with pytest.raises(ConfigError):
        config.load(p)


def test_adapters_default_in_file_cfg_is_none(tmp_path):
    assert config.load(tmp_path / "absent.ini").adapters is None


def test_adapters_named_in_file_cfg(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = claude, cursor\n")
    assert config.load(p).adapters == frozenset({"claude", "cursor"})


def test_adapters_wildcard_in_file_cfg_is_none(tmp_path):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = *\n")
    assert config.load(p).adapters is None


# --- adapters whitelist wired end-to-end (0.16.0) --------------------------


def test_doctor_respects_adapter_whitelist(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = fake\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fake" in out
    assert "fake_stdin" not in out


def test_doctor_excludes_all_when_unknown_whitelist(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = nonexistent-adapter\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no client adapters" in out


# --- status command: adapter whitelist display (0.16.0) --------------------


def test_status_json_adapters_null_when_not_configured(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "absent.ini"))
    rc = main(["status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["adapters"] is None


def test_status_json_adapters_sorted_list_when_configured(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = fake_stdin, fake\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["status", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["adapters"] == ["fake", "fake_stdin"]


def test_status_text_shows_all_active_when_not_configured(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "absent.ini"))
    rc = main(["status"])
    assert rc == 0
    assert "* (all active)" in capsys.readouterr().out


def test_status_text_shows_named_adapters_when_configured(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = fake\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fake" in out and "from config" in out


# --- run / alias: excluded adapter → clear error (0.16.0) ------------------


def test_run_excluded_adapter_returns_error_4(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = fake_stdin\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["run", "--client", "fake", "--model", "m", "--prompt", "STDOUT hi"])
    assert rc == 4
    assert "fake" in capsys.readouterr().err


def test_alias_excluded_adapter_returns_error_4(tmp_path, monkeypatch, capsys):
    p = _write(tmp_path / "c.ini", "[defaults]\nadapters = fake_stdin\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(p))
    rc = main(["alias", "fake", "--", "-c", "print('hi')"])
    assert rc == 4
    assert "fake" in capsys.readouterr().err


# --- init ------------------------------------------------------------------


def test_init_writes_config_and_is_idempotent(tmp_path):
    target = tmp_path / "cfg" / "config.ini"
    path, created = config.write_default_config(target)
    assert created is True and path == target and target.is_file()
    # the written file parses and pins the store at the resolved default
    assert config.load(target).store == str(config.default_store_path())
    # a second call never overwrites
    again_path, again_created = config.write_default_config(target)
    assert again_path == target and again_created is False
