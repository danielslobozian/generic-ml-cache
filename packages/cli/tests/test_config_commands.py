# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for gmlcache config validate and config show."""

from __future__ import annotations

import json
from pathlib import Path

from generic_ml_cache_cli.cli import main  # type: ignore[attr-defined]
from generic_ml_cache_cli.config import validate


def run(args):
    return main(args)


def write_config(tmp_path: Path, content: str) -> Path:
    cfg = tmp_path / "config.ini"
    cfg.write_text(content, encoding="utf-8")
    return cfg


# ---------------------------------------------------------------------------
# validate() unit tests — the function directly
# ---------------------------------------------------------------------------


def test_validate_missing_file_returns_no_issues(tmp_path):
    issues = validate(tmp_path / "no-such.ini")
    assert issues == []


def test_validate_empty_file_returns_no_issues(tmp_path):
    cfg = write_config(tmp_path, "")
    assert validate(cfg) == []


def test_validate_valid_config_returns_no_issues(tmp_path):
    cfg = write_config(
        tmp_path,
        "[defaults]\nmode = cache\npersist = cache\ntimeout = 30\nversion = 1\n",
    )
    assert validate(cfg) == []


def test_validate_invalid_mode_is_error(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\nmode = bogus\n")
    issues = validate(cfg)
    errors = [i for i in issues if i.severity == "error" and i.key == "mode"]
    assert errors


def test_validate_invalid_persist_is_error(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\npersist = nope\n")
    issues = validate(cfg)
    assert any(i.severity == "error" and i.key == "persist" for i in issues)


def test_validate_invalid_timeout_is_error(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\ntimeout = not-a-number\n")
    issues = validate(cfg)
    assert any(i.severity == "error" and i.key == "timeout" for i in issues)


def test_validate_invalid_trust_scan_is_error(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\ntrust_scan = maybe\n")
    issues = validate(cfg)
    assert any(i.severity == "error" and i.key == "trust_scan" for i in issues)


def test_validate_invalid_max_size_is_error(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\nmax_size = 5zettabytes\n")
    issues = validate(cfg)
    assert any(i.severity == "error" and i.key == "max_size" for i in issues)


def test_validate_invalid_max_age_is_error(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\nmax_age = forever\n")
    issues = validate(cfg)
    assert any(i.severity == "error" and i.key == "max_age" for i in issues)


def test_validate_invalid_log_level_is_error(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\nlog_level = VERBOSE\n")
    issues = validate(cfg)
    assert any(i.severity == "error" and i.key == "log_level" for i in issues)


def test_validate_unknown_key_is_warning(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\nunknown_key = 42\n")
    issues = validate(cfg)
    assert any(i.severity == "warning" and i.key == "unknown_key" for i in issues)


def test_validate_unknown_section_is_warning(tmp_path):
    cfg = write_config(tmp_path, "[custom_section]\nfoo = bar\n")
    issues = validate(cfg)
    assert any(i.severity == "warning" and "custom_section" in i.message for i in issues)


def test_validate_wrong_version_is_warning(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\nversion = 99\n")
    issues = validate(cfg)
    assert any(i.severity == "warning" and i.key == "version" for i in issues)


def test_validate_correct_version_is_clean(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\nversion = 1\n")
    issues = validate(cfg)
    assert not any(i.key == "version" for i in issues)


def test_validate_collects_multiple_errors(tmp_path):
    cfg = write_config(tmp_path, "[defaults]\nmode = bad\npersist = bad\n")
    errors = [i for i in validate(cfg) if i.severity == "error"]
    assert len(errors) >= 2


# ---------------------------------------------------------------------------
# gmlcache config validate — CLI integration
# ---------------------------------------------------------------------------


def test_cli_validate_no_config_exits_zero(capsys):
    rc = run(["config", "validate"])
    assert rc == 0


def test_cli_validate_valid_config_exits_zero(tmp_path, capsys, monkeypatch):
    cfg = write_config(tmp_path, "[defaults]\nmode = cache\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(cfg))
    rc = run(["config", "validate"])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_cli_validate_bad_config_exits_four(tmp_path, monkeypatch, capsys):
    cfg = write_config(tmp_path, "[defaults]\nmode = garbage\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(cfg))
    rc = run(["config", "validate"])
    assert rc == 4
    assert "error" in capsys.readouterr().out


def test_cli_validate_json_valid(tmp_path, monkeypatch, capsys):
    cfg = write_config(tmp_path, "[defaults]\nmode = cache\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(cfg))
    rc = run(["config", "validate", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["valid"] is True
    assert data["issues"] == []


def test_cli_validate_json_invalid(tmp_path, monkeypatch, capsys):
    cfg = write_config(tmp_path, "[defaults]\nmode = garbage\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(cfg))
    rc = run(["config", "validate", "--json"])
    assert rc == 4
    data = json.loads(capsys.readouterr().out)
    assert data["valid"] is False
    assert any(i["severity"] == "error" and i["key"] == "mode" for i in data["issues"])


def test_cli_validate_json_warnings_do_not_set_exit_four(tmp_path, monkeypatch, capsys):
    cfg = write_config(tmp_path, "[defaults]\nversion = 99\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(cfg))
    rc = run(["config", "validate", "--json"])
    # warnings alone → still valid (no errors), exit 0
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["valid"] is True
    assert any(i["severity"] == "warning" for i in data["issues"])


# ---------------------------------------------------------------------------
# gmlcache config show — CLI integration
# ---------------------------------------------------------------------------


def test_cli_show_exits_zero(capsys):
    rc = run(["config", "show"])
    assert rc == 0


def test_cli_show_prints_all_keys(capsys):
    rc = run(["config", "show"])
    assert rc == 0
    out = capsys.readouterr().out
    for key in ("mode", "persist", "store", "timeout", "trust_scan"):
        assert key in out


def test_cli_show_prints_source(capsys):
    rc = run(["config", "show"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "default" in out


def test_cli_show_resolved_flag_accepted(capsys):
    rc = run(["config", "show", "--resolved"])
    assert rc == 0


def test_cli_show_json_valid(capsys):
    rc = run(["config", "show", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "settings" in data
    assert "mode" in data["settings"]
    assert "source" in data["settings"]["mode"]


def test_cli_show_json_reflects_env(monkeypatch, capsys):
    monkeypatch.setenv("GMLCACHE_MODE", "offline")
    rc = run(["config", "show", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["settings"]["mode"]["value"] == "offline"
    assert data["settings"]["mode"]["source"] == "env"


def test_cli_show_json_reflects_config_file(tmp_path, monkeypatch, capsys):
    cfg = write_config(tmp_path, "[defaults]\ntimeout = 999\n")
    monkeypatch.setenv("GMLCACHE_CONFIG", str(cfg))
    rc = run(["config", "show", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["settings"]["timeout"]["value"] == 999.0
    assert data["settings"]["timeout"]["source"] == "config"
