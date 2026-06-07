# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json

import pytest

from generic_ml_cache import config
from generic_ml_cache.cli import main
from generic_ml_cache.errors import ConfigError


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
    assert settings["store"] == (".gmlcache", "default")
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
