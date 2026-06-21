# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import sys

from generic_ml_cache_cli.cli import main
from generic_ml_cache_core.adapter.out.client.discover import probe, probe_all


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
