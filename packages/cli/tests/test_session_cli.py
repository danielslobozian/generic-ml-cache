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


def test_session_report_rolls_up_invocations_executions_hits(capsys):
    run = _RUN + ["--session", "wf"]
    main(run)  # miss -> record (a real execution)
    main(run)  # same input -> hit (no execution)
    capsys.readouterr()

    assert main(["session", "report", "wf"]) == 0
    out = capsys.readouterr().out
    assert "invocations : 2   executions : 1   hits : 1" in out
    assert "by provider / model:" in out and "fake / m1" in out
    assert "by day (activity):" in out
    # no dollars anywhere in the render (cost is a client-specific advisory estimate)
    assert "$" not in out and "cost" not in out.lower()


def test_session_report_json(capsys):
    import json

    main(_RUN + ["--session", "wf"])  # one record (the fake client reports no usage)
    capsys.readouterr()
    assert main(["session", "report", "wf", "--json"]) == 0
    out = capsys.readouterr().out
    assert "cost" not in out.lower() and "usd" not in out.lower() and "$" not in out
    data = json.loads(out)
    assert data["session"] == "wf"
    assert (data["invocations"], data["executions"], data["hits"]) == (1, 1, 0)
    assert data["unknown_usage"] == 1
    assert data["span"]["days"] == 1
    assert data["by_model"] == [
        {
            "client": "fake",
            "model": "m1",
            "spent_input": 0,
            "spent_output": 0,
            "spent_tokens": 0,
            "saved_tokens": 0,
            "executions": 1,
            "hits": 0,
        }
    ]
    assert len(data["by_day"]) == 1 and data["by_day"][0]["invocations"] == 1


def test_session_report_unknown_session_is_clean(capsys):
    assert main(["session", "report", "nope"]) == 0
    assert "no events" in capsys.readouterr().out
