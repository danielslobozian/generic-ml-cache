# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""`run --json`: a machine-readable envelope (status/exit/files/usage/stdout) for a
parent process -- e.g. the workflow engine reading normalized usage after a real
execution. Usage comes from the same normalized envelope `check --json` exposes."""

from __future__ import annotations

import json

from generic_ml_cache.cli import main

_CLI = ["--client", "fake", "--model", "m", "--effort", "high"]


def test_run_json_records_then_hits(capsys):
    # First run records -> envelope reports recorded, not cached, exit 0.
    assert main(["run", *_CLI, "--prompt", "STDOUT hi", "--json"]) == 0
    p1 = json.loads(capsys.readouterr().out)
    assert p1["status"] == "recorded"
    assert p1["cached"] is False
    assert p1["exit"] == 0
    assert p1["client"] == "fake"
    # the usage field is always present (null for a client that reports none,
    # the normalized dict for a real client) -- this is the 0.0.10 hook.
    assert "usage" in p1
    assert "files" in p1 and "stdout" in p1

    # Second run of the same request is a hit, replayed from the cassette.
    assert main(["run", *_CLI, "--prompt", "STDOUT hi", "--json"]) == 0
    p2 = json.loads(capsys.readouterr().out)
    assert p2["status"] == "hit"
    assert p2["cached"] is True
    assert p2["exit"] == 0


def test_run_without_json_still_prints_raw_answer(capsys):
    # Back-compat: no --json keeps the raw answer on stdout (not an envelope).
    assert main(["run", *_CLI, "--prompt", "STDOUT hello"]) == 0
    out = capsys.readouterr().out
    # raw answer, not JSON -- it must not parse as the envelope object
    try:
        parsed = json.loads(out)
        assert not (isinstance(parsed, dict) and "status" in parsed)
    except json.JSONDecodeError:
        pass  # expected: raw text, not JSON
