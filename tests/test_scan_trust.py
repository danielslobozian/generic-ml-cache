# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Scan-trust: the opt-in that makes allow-path calls cacheable (0.0.5)."""

from __future__ import annotations

import pytest

from generic_ml_cache import config as C
from generic_ml_cache.cli import main
from generic_ml_cache.common.errors import ConfigError


def _run_args(folder, prompt="STDOUT hi"):
    return [
        "run",
        "--client",
        "fake",
        "--model",
        "m",
        "--prompt",
        prompt,
        "--allow-path",
        str(folder),
    ]


# --- config parsing ---------------------------------------------------------


def test_config_trust_scan_true(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text("[defaults]\ntrust_scan = true\n")
    assert C.load(p).trust_scan is True


def test_config_trust_scan_false(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text("[defaults]\ntrust_scan = no\n")
    assert C.load(p).trust_scan is False


def test_config_trust_scan_invalid(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text("[defaults]\ntrust_scan = maybe\n")
    with pytest.raises(ConfigError):
        C.load(p)


def test_trust_scan_default_is_false(tmp_path, monkeypatch):
    monkeypatch.delenv("GMLCACHE_TRUST_SCAN", raising=False)
    p = tmp_path / "config.ini"
    p.write_text("[defaults]\nmode = cache\n")
    fc = C.load(p)
    assert fc.trust_scan is None  # unset in the file
    value, source = C.resolve_settings(fc)["trust_scan"]
    assert value is False and source == "default"


def test_env_overrides_config_trust_scan(tmp_path, monkeypatch):
    p = tmp_path / "config.ini"
    p.write_text("[defaults]\ntrust_scan = false\n")
    fc = C.load(p)
    monkeypatch.setenv("GMLCACHE_TRUST_SCAN", "true")
    value, source = C.resolve_settings(fc)["trust_scan"]
    assert value is True and source == "env"


# --- end-to-end CLI behaviour ----------------------------------------------


def test_allow_path_passthrough_without_trust(tmp_path, monkeypatch):
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "none.ini"))  # no config file
    monkeypatch.delenv("GMLCACHE_TRUST_SCAN", raising=False)
    folder = tmp_path / "repo"
    folder.mkdir()
    store = C.default_store_path()
    args = _run_args(folder)

    assert main(args) == 0
    assert list(store.glob("**/*.json")) == []  # passthrough: nothing stored
    assert main(args + ["--offline"]) == 3  # and cannot be served offline


def test_trust_scan_caches_allow_path(tmp_path, monkeypatch):
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "none.ini"))
    monkeypatch.setenv("GMLCACHE_TRUST_SCAN", "true")
    folder = tmp_path / "repo"
    folder.mkdir()
    store = C.default_store_path()
    args = _run_args(folder)

    assert main(args) == 0
    assert len(list(store.glob("**/*.json"))) == 1  # cached despite allow-path
    assert main(args + ["--offline"]) == 0  # now served as a hit


def test_status_shows_trust_scan(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "none.ini"))
    monkeypatch.setenv("GMLCACHE_TRUST_SCAN", "true")
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "trust_scan" in out and "true" in out and "from env" in out
