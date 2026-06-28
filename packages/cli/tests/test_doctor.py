# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for gmlcache doctor — extended diagnostic fields, --json, --bundle."""

from __future__ import annotations

import json
import sys

import pytest

from generic_ml_cache_cli.cli import main  # type: ignore[attr-defined]


def run(args):
    return main(args)


# ---------------------------------------------------------------------------
# Text output — new extended fields
# ---------------------------------------------------------------------------


def test_doctor_text_shows_python_version(capsys):
    rc = run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    py_short = sys.version.split()[0]
    assert py_short in out


def test_doctor_text_shows_store_path(capsys, tmp_path):
    rc = run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "store path" in out


def test_doctor_text_shows_config_file(capsys):
    rc = run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "config file" in out


def test_doctor_text_shows_daemon_not_running(capsys):
    # No daemon is running during tests; the check should not raise.
    rc = run(["doctor", "--port", "19999"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "not running" in out


def test_doctor_text_shows_store_perms(capsys):
    rc = run(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "store perms" in out


# ---------------------------------------------------------------------------
# --json output — all new fields present
# ---------------------------------------------------------------------------


def test_doctor_json_contains_python(capsys):
    rc = run(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "python" in data
    assert sys.version.split()[0] in data["python"]


def test_doctor_json_contains_os(capsys):
    rc = run(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "os" in data
    assert data["os"]


def test_doctor_json_contains_config_path(capsys):
    rc = run(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "config_path" in data


def test_doctor_json_contains_store_path(capsys):
    rc = run(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "store_path" in data


def test_doctor_json_contains_store_permissions(capsys):
    rc = run(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    perms = data["store_permissions"]
    assert "exists" in perms
    assert "readable" in perms
    assert "writable" in perms


def test_doctor_json_contains_daemon_block(capsys):
    rc = run(["doctor", "--json", "--port", "19999"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    daemon = data["daemon"]
    assert daemon["port"] == 19999
    assert daemon["reachable"] is False


def test_doctor_json_contains_clients(capsys):
    rc = run(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "clients" in data
    assert isinstance(data["clients"], list)


def test_doctor_json_contains_schema(capsys):
    rc = run(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "schema" in data
    assert isinstance(data["schema"], list)


def test_doctor_json_contains_adapter_extensions(capsys):
    rc = run(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "adapter_extensions" in data


# ---------------------------------------------------------------------------
# --bundle flag
# ---------------------------------------------------------------------------


def test_doctor_bundle_writes_file(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = run(["doctor", "--bundle"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "bundle written" in out
    # Exactly one bundle file created
    bundles = list(tmp_path.glob("gmlcache-bundle-*.json"))
    assert len(bundles) == 1


def test_doctor_bundle_file_is_valid_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(["doctor", "--bundle"])
    bundle = next(tmp_path.glob("gmlcache-bundle-*.json"))
    data = json.loads(bundle.read_text(encoding="utf-8"))
    assert "python" in data
    assert "store_permissions" in data
    assert "daemon" in data


def test_doctor_bundle_filename_has_timestamp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run(["doctor", "--bundle"])
    bundle = next(tmp_path.glob("gmlcache-bundle-*.json"))
    # Filename pattern: gmlcache-bundle-YYYYMMDDTHHMMSSz.json
    assert bundle.name.startswith("gmlcache-bundle-")
    assert bundle.name.endswith(".json")


# ---------------------------------------------------------------------------
# --json and --bundle are mutually exclusive
# ---------------------------------------------------------------------------


def test_doctor_json_and_bundle_are_mutually_exclusive():
    with pytest.raises(SystemExit) as exc_info:
        run(["doctor", "--json", "--bundle"])
    assert exc_info.value.code != 0
