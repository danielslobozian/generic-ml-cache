# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CLI tests for sessions: run --session / GMLCACHE_SESSION and `session start`."""

from __future__ import annotations

import glob
import sqlite3

from generic_ml_cache_cli.cli import main

_RUN = ["run", "--client", "fake", "--model", "m1", "--effort", "high", "--prompt", "STDOUT hi"]


def _session_ids(tmp_path):
    dbs = glob.glob(str(tmp_path / "**" / "registry.sqlite3"), recursive=True)
    if not dbs:
        return []
    conn = sqlite3.connect(dbs[0])
    try:
        return [r[0] for r in conn.execute("SELECT session_id FROM access_events ORDER BY id")]
    finally:
        conn.close()


def test_run_with_session_flag_records_the_session_id(tmp_path, capsys):
    assert main(_RUN + ["--session", "workflow-1"]) == 0
    capsys.readouterr()
    assert _session_ids(tmp_path) == ["workflow-1"]


def test_run_reads_session_from_env(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GMLCACHE_SESSION", "env-session")
    assert main(_RUN) == 0
    capsys.readouterr()
    assert _session_ids(tmp_path) == ["env-session"]


def test_flag_wins_over_env(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GMLCACHE_SESSION", "env-session")
    assert main(_RUN + ["--session", "flag-session"]) == 0
    capsys.readouterr()
    assert _session_ids(tmp_path) == ["flag-session"]


def test_run_without_a_session_records_null(tmp_path, capsys):
    assert main(_RUN) == 0
    capsys.readouterr()
    assert _session_ids(tmp_path) == [None]


def test_session_start_prints_a_scriptable_id(capsys):
    assert main(["session", "start"]) == 0
    out = capsys.readouterr().out.strip()
    assert out and " " not in out  # a single bare id, usable as $(gmlcache session start)
    # two starts yield distinct ids
    main(["session", "start"])
    assert capsys.readouterr().out.strip() != out


def test_bare_session_shows_usage(capsys):
    assert main(["session"]) == 2
    assert "session start" in capsys.readouterr().err
