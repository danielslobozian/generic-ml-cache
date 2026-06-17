# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""`gmlcache stats` reports how many cassettes are stored, their size split by
client/model, and the access-event counts -- the diagnostic that lets a user
decide whether to switch on an eviction policy."""

from __future__ import annotations

import json

from generic_ml_cache.cli import main


def _run(model: str, prompt: str) -> int:
    return main(
        ["run", "--client", "fake", "--model", model, "--effort", "high", "--prompt", prompt]
    )


def test_stats_text_reports_counts_and_access(capsys):
    assert _run("m1", "STDOUT one") == 0
    assert _run("m2", "STDOUT two") == 0
    capsys.readouterr()  # discard the run output

    assert main(["stats"]) == 0
    out = capsys.readouterr().out
    assert "cassettes : 2" in out
    assert "m1" in out and "m2" in out
    assert "record=2" in out  # both were fresh records


def test_stats_json_breaks_down_by_client_model(capsys):
    assert _run("m1", "STDOUT one") == 0
    capsys.readouterr()

    assert main(["stats", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["cassettes"] == 1
    assert data["bytes"] > 0
    assert data["by_client_model"][0]["client"] == "fake"
    assert data["by_client_model"][0]["model"] == "m1"
    assert data["access_events"].get("record") == 1


def test_stats_on_empty_store_is_clean(capsys):
    assert main(["stats"]) == 0
    out = capsys.readouterr().out
    assert "cassettes : 0" in out
