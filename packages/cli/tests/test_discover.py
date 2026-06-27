# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import subprocess
import sys

from generic_ml_cache_cli.cli import main
from generic_ml_cache_core.adapter.out.client.discover import (
    list_models,
    list_models_all,
    probe,
    probe_all,
)


def test_probe_present_client_reports_version():
    # the test 'fake' adapter runs the python interpreter, so it is always present
    s = probe("fake")
    assert s.present is True
    assert s.executable == sys.executable
    assert s.version and "Python" in s.version  # `python --version`


def test_probe_absent_executable_is_not_present():
    s = probe("fake", executable="definitely-not-a-real-binary-xyz123")
    assert s.present is False
    assert "could not find" in (s.detail or "")


def test_probe_all_includes_registered_fake():
    names = {s.name for s in probe_all()}
    assert "fake" in names


def test_probe_all_threads_executables_mapping():
    # an executables mapping overrides per client; an absent binary -> not present
    statuses = {s.name: s for s in probe_all(executables={"fake": "no-such-binary-xyz123"})}
    assert statuses["fake"].present is False


def test_doctor_cli_lists_clients(capsys):
    rc = main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "fake" in out
    assert "present" in out


def test_doctor_shows_schema_not_initialised_on_fresh_store(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    rc = main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "store schema" in out
    assert "not initialised" in out


def test_doctor_shows_schema_version_after_first_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    main(["run", "--client", "fake", "--model", "m", "--effort", "e", "--prompt", "STDOUT hi"])
    capsys.readouterr()
    rc = main(["doctor"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "store schema" in out
    assert "0001.unified-schema" in out
    assert "migration(s) applied" in out


def test_doctor_json_includes_schema_key(tmp_path, monkeypatch, capsys):
    import json

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    main(["run", "--client", "fake", "--model", "m", "--effort", "e", "--prompt", "STDOUT hi"])
    capsys.readouterr()
    rc = main(["doctor", "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert "clients" in data and "schema" in data
    assert any(m["migration_id"] == "0001.unified-schema" for m in data["schema"])


# --- list_models --------------------------------------------------------------


def test_list_models_returns_not_present_for_absent_executable():
    result = list_models("cursor", executable="definitely-not-a-real-binary-xyz123")
    assert result.present is False
    assert result.supported is False


def test_list_models_returns_reason_when_subprocess_raises(monkeypatch):
    def _raise_oserror(*args, **kwargs):
        raise OSError("cannot exec")

    monkeypatch.setattr(subprocess, "run", _raise_oserror)
    result = list_models("cursor", executable=sys.executable)
    assert result.present is True
    assert result.supported is True
    assert result.models is None
    assert "cannot exec" in (result.reason or "")


def test_list_models_returns_reason_on_nonzero_exit(monkeypatch):
    class _FailedProcess:
        returncode = 1
        stderr = "unknown flag: --list-models"
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FailedProcess())
    result = list_models("cursor", executable=sys.executable)
    assert result.present is True
    assert result.supported is True
    assert result.models is None
    assert result.reason is not None


def test_list_models_all_returns_listing_for_every_registered_client():
    results = list_models_all()
    assert isinstance(results, list)
    assert len(results) >= 1


# --- _probe_version failure path via probe() ----------------------------------


def test_probe_reports_version_check_failed_when_subprocess_raises(monkeypatch):
    def _raise_oserror(*args, **kwargs):
        raise OSError("no such binary")

    monkeypatch.setattr(subprocess, "run", _raise_oserror)
    status = probe("fake")
    assert status.present is True
    assert status.version is None
    assert "version check failed" in (status.detail or "")


# --- whitelist filtering (0.16.0) -------------------------------------------


def test_probe_all_whitelist_restricts_to_named_adapters():
    # Only the 'fake' adapter is in the whitelist; 'fake_stdin' and others must be absent.
    results = probe_all(whitelist=frozenset({"fake"}))
    names = {s.name for s in results}
    assert "fake" in names
    assert "fake_stdin" not in names


def test_probe_all_none_whitelist_returns_all_local_adapters():
    no_filter = probe_all(whitelist=None)
    filtered = probe_all(whitelist=frozenset({"fake"}))
    assert len(no_filter) > len(filtered)


def test_list_models_all_whitelist_restricts_to_named_adapters():
    results = list_models_all(whitelist=frozenset({"fake"}))
    names = {m.name for m in results}
    assert "fake" in names
    assert "fake_stdin" not in names


def test_list_models_whitelist_blocks_excluded_adapter():
    from generic_ml_cache_core.common.errors import UnknownClient
    import pytest

    with pytest.raises(UnknownClient, match="unknown adapter"):
        list_models("fake_stdin", whitelist=frozenset({"fake"}))
