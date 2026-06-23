# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations


import pytest

from generic_ml_cache_cli.cli import main
from conftest import write_directive


def run_cli(args):
    return main(args)


def test_cli_records_then_replays_offline(tmp_path, capsys):
    common = [
        "run",
        "--client",
        "fake",
        "--model",
        "m1",
        "--effort",
        "high",
    ]

    rc = run_cli(common + ["--prompt", "STDOUT hello"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "hello" in out

    # now offline must succeed from cache
    rc = run_cli(common + ["--prompt", "STDOUT hello", "--offline"])
    assert rc == 0


def test_cli_offline_miss_exits_3(tmp_path, capsys):
    rc = run_cli(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--prompt",
            "STDOUT x",
            "--offline",
        ]
    )
    assert rc == 3
    assert "offline miss" in capsys.readouterr().err


def test_cli_propagates_exit_code(tmp_path):
    rc = run_cli(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--prompt",
            "EXIT 5",
        ]
    )
    assert rc == 5


def test_cli_writes_files_to_cwd(tmp_path, monkeypatch):
    # No --output-dir: the cache writes into the directory it was called in,
    # exactly as the real client would. Control that by chdir-ing into a workdir.
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    rc = run_cli(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--prompt",
            write_directive("deep/file.txt", "data\n"),
        ]
    )
    assert rc == 0
    assert (workdir / "deep" / "file.txt").read_text(encoding="utf-8") == "data\n"


# --- cross-platform invariants --------------------------------------------


def test_multibyte_unicode_roundtrips_through_a_run(tmp_path, monkeypatch):
    """A file the client produces with multibyte content materialises byte-exact."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    text = "café — 日本語 — \temoji 🚀\n"
    rc = run_cli(
        ["run", "--client", "fake", "--model", "m1", "--prompt", write_directive("u.txt", text)]
    )
    assert rc == 0
    assert (workdir / "u.txt").read_text(encoding="utf-8") == text


def test_cli_init_creates_config_then_idempotent(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "cfg.ini"
    monkeypatch.setenv("GMLCACHE_CONFIG", str(cfg))
    assert run_cli(["init"]) == 0
    out = capsys.readouterr().out
    assert "created config" in out and str(cfg) in out
    assert cfg.is_file()
    # idempotent: a second init leaves the file unchanged
    assert run_cli(["init"]) == 0
    assert "already present" in capsys.readouterr().out


def test_run_rejects_retired_location_flags(tmp_path):
    base = ["run", "--client", "fake", "--model", "m", "--prompt", "STDOUT hi"]
    for bad in (["--store", str(tmp_path)], ["--output-dir", str(tmp_path)]):
        with pytest.raises(SystemExit):
            run_cli(base + bad)


# --- banner & bare invocation ---------------------------------------------


def test_render_banner_lines_align():
    from generic_ml_cache_cli.cli import render_banner

    lines = render_banner(color=False).splitlines()
    widths = {len(line) for line in lines}
    assert len(widths) == 1  # every box line (top, four mark rows, bottom) is one width
    assert len(lines) == 6  # the mark adds four bar rows inside the box
    assert "═" in render_banner(color=False)  # the hollow mark renders


def test_render_banner_color_is_opt_in():
    from generic_ml_cache_cli.cli import render_banner

    assert "\x1b[" not in render_banner(color=False)
    assert "\x1b[" in render_banner(color=True)


def test_paint_colours_only_when_enabled(monkeypatch):
    """gmlcache's UI is coloured only on a real TTY; piped/NO_COLOR output is plain."""
    import generic_ml_cache_cli.cli as climod

    monkeypatch.setattr(climod, "_use_color", lambda: True)
    painted = climod._paint("hit", climod._GREEN)
    assert painted.startswith("\x1b[") and painted.endswith("\x1b[0m") and "hit" in painted

    monkeypatch.setattr(climod, "_use_color", lambda: False)
    assert climod._paint("hit", climod._GREEN) == "hit"  # no escape codes when off


def test_bare_invocation_prints_help_not_an_error(capsys):
    rc = main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "gmlcache" in out
    assert "record · replay · check · sessions · encryption" in out
    assert "usage:" in out


def test_bare_invocation_has_no_ansi_when_not_a_tty(capsys):
    main([])
    # capsys stdout is not a terminal, so the banner must be plain text
    assert "\x1b[" not in capsys.readouterr().out


def test_help_flag_shows_the_banner(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["-h"])
    assert excinfo.value.code == 0
    assert "record · replay · check · sessions · encryption" in capsys.readouterr().out


# --- list (grouped by client/model) ---------------------------------------


def _record_two_models(monkeypatch, tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    for model in ("m1", "m2"):
        run_cli(
            [
                "run",
                "--client",
                "fake",
                "--model",
                model,
                "--effort",
                "high",
                "--prompt",
                write_directive(f"{model}.txt", "hi\n"),
            ]
        )


def test_list_empty_store_is_clean(capsys):
    rc = main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no current executions" in out


def test_list_groups_by_client_model(tmp_path, monkeypatch, capsys):
    _record_two_models(monkeypatch, tmp_path)
    capsys.readouterr()
    rc = main(["list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "fake" in out
    assert "m1" in out
    assert "m2" in out


def test_list_model_filter(tmp_path, monkeypatch, capsys):
    _record_two_models(monkeypatch, tmp_path)
    capsys.readouterr()
    rc = main(["list", "--model", "m1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "m1" in out
    assert "m2" not in out


def test_list_json(tmp_path, monkeypatch, capsys):
    import json

    _record_two_models(monkeypatch, tmp_path)
    capsys.readouterr()
    rc = main(["list", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    models = {entry["model"] for entry in data["executions"]}
    assert models == {"m1", "m2"}
    assert "key" in data["executions"][0]


def test_main_offers_the_parser_to_argcomplete(monkeypatch):
    import generic_ml_cache_cli.cli as cli

    if cli.argcomplete is None:
        pytest.skip("argcomplete not installed")
    seen = []
    monkeypatch.setattr(cli.argcomplete, "autocomplete", lambda parser: seen.append(parser))
    main([])  # a normal run must still work; autocomplete is a no-op here
    assert len(seen) == 1


def test_list_shows_hit_counts(tmp_path, monkeypatch, capsys):
    import json

    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    prompt = write_directive("h.txt", "hi\n")
    run_cli(["run", "--client", "fake", "--model", "m1", "--effort", "high", "--prompt", prompt])
    run_cli(["run", "--client", "fake", "--model", "m1", "--effort", "high", "--prompt", prompt])
    capsys.readouterr()

    assert main(["list"]) == 0
    assert "hits:1" in capsys.readouterr().out

    assert main(["list", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["executions"][0]["hits"] == 1


def test_inspect_by_short_key(tmp_path, monkeypatch, capsys):
    import json

    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    run_cli(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--prompt",
            write_directive("k.txt", "hi\n"),
        ]
    )
    capsys.readouterr()
    main(["list", "--json"])
    short_key = json.loads(capsys.readouterr().out)["executions"][0]["key"][:12]

    capsys.readouterr()
    rc = main(["inspect", short_key])  # short key alone is enough
    out = capsys.readouterr().out
    assert rc == 0
    assert short_key in out
    assert "kind   : local_managed" in out


def test_stats_reports_executions_and_access(tmp_path, monkeypatch, capsys):
    _record_two_models(monkeypatch, tmp_path)
    capsys.readouterr()
    assert main(["stats"]) == 0
    out = capsys.readouterr().out
    assert "executions : 2" in out
    assert "record" in out  # access events


def test_check_reports_hit_after_a_run(tmp_path, monkeypatch, capsys):
    workdir = tmp_path / "work"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    args = ["--client", "fake", "--model", "m1", "--effort", "high", "--prompt", "STDOUT hi"]
    run_cli(["run", *args])
    capsys.readouterr()
    rc = main(["check", *args])
    out = capsys.readouterr().out
    assert rc == 0
    assert "status  : hit" in out


def test_run_tag_stores_tags_through_the_cli(tmp_path):
    import glob
    import sqlite3

    rc = run_cli(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--prompt",
            "STDOUT hi",
            "--tag",
            "ticket",
            "--tag",
            "id-scan",
        ]
    )
    assert rc == 0
    stores = glob.glob(str(tmp_path / "**" / "executions.sqlite3"), recursive=True)
    assert stores, "no executions store was written"
    connection = sqlite3.connect(stores[0])
    stored = sorted(tag for (tag,) in connection.execute("SELECT tag FROM execution_tags"))
    connection.close()
    assert stored == ["id-scan", "ticket"]


def test_list_filters_by_tag_and_shows_tags(capsys):
    import json

    base = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(base + ["--prompt", "STDOUT a", "--tag", "alpha"])
    run_cli(base + ["--prompt", "STDOUT b", "--tag", "beta"])
    capsys.readouterr()

    rc = main(["list", "--tag", "alpha", "--json"])
    assert rc == 0
    listed = json.loads(capsys.readouterr().out)["executions"]
    assert len(listed) == 1  # match-any filter keeps only the alpha-tagged entry
    assert listed[0]["tags"] == ["alpha"]


def test_list_excludes_by_tag(capsys):
    import json

    base = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(base + ["--prompt", "STDOUT a", "--tag", "alpha"])
    run_cli(base + ["--prompt", "STDOUT b", "--tag", "beta"])
    capsys.readouterr()

    rc = main(["list", "--exclude-tag", "beta", "--json"])
    assert rc == 0
    listed = json.loads(capsys.readouterr().out)["executions"]
    assert len(listed) == 1  # the beta-tagged entry is dropped
    assert listed[0]["tags"] == ["alpha"]


def test_list_exclude_tag_overrides_include(capsys):
    import json

    base = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    # one entry carrying both tags
    run_cli(base + ["--prompt", "STDOUT a", "--tag", "alpha", "--tag", "beta"])
    capsys.readouterr()

    rc = main(["list", "--tag", "alpha", "--exclude-tag", "beta", "--json"])
    assert rc == 0
    listed = json.loads(capsys.readouterr().out)["executions"]
    assert listed == []  # exclude wins when a tag is both included and excluded


def test_tags_lists_distinct_tags_with_counts(capsys):
    import json

    base = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(base + ["--prompt", "STDOUT a", "--tag", "alpha", "--tag", "shared"])
    run_cli(base + ["--prompt", "STDOUT b", "--tag", "beta", "--tag", "shared"])
    capsys.readouterr()

    rc = main(["tags", "--json"])
    assert rc == 0
    tags = json.loads(capsys.readouterr().out)["tags"]
    assert tags == [
        {"tag": "alpha", "count": 1},
        {"tag": "beta", "count": 1},
        {"tag": "shared", "count": 2},
    ]


def test_tags_empty_when_no_tags(capsys):
    base = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(base + ["--prompt", "STDOUT a"])
    capsys.readouterr()

    rc = main(["tags"])
    assert rc == 0
    assert "no tags" in capsys.readouterr().out


def test_persist_meter_stores_no_output_so_offline_misses(capsys):
    common = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    # meter records the run but keeps no output ...
    rc = run_cli(common + ["--prompt", "STDOUT hello", "--persist", "meter"])
    assert rc == 0
    assert "hello" in capsys.readouterr().out

    # ... so there is nothing servable: a later offline call misses (exit 3).
    rc = run_cli(common + ["--prompt", "STDOUT hello", "--offline"])
    assert rc == 3
    assert "offline miss" in capsys.readouterr().err


def test_persist_default_cache_replays_offline(capsys):
    common = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    # default depth is cache: output is stored ...
    run_cli(common + ["--prompt", "STDOUT hello", "--persist", "cache"])
    capsys.readouterr()
    # ... so a later offline call replays from cache.
    rc = run_cli(common + ["--prompt", "STDOUT hello", "--offline"])
    assert rc == 0


def _only_key(capsys):
    import json

    main(["list", "--json"])
    return json.loads(capsys.readouterr().out)["executions"][0]["key"]


def test_persist_dataset_stores_input_visible_in_inspect(capsys):
    common = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(common + ["--prompt", "STDOUT hi", "--context", "some context", "--persist", "dataset"])
    capsys.readouterr()

    # dataset still replays output normally ...
    rc = run_cli(common + ["--prompt", "STDOUT hi", "--context", "some context", "--offline"])
    assert rc == 0
    capsys.readouterr()

    # ... and inspect shows the input was stored (prompt + context parts).
    rc = main(["inspect", _only_key(capsys)[:12]])
    assert rc == 0
    out = capsys.readouterr().out
    assert "input  : stored" in out
    assert "prompt" in out and "context" in out


def test_persist_cache_does_not_store_input_in_inspect(capsys):
    common = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(common + ["--prompt", "STDOUT hi", "--persist", "cache"])
    capsys.readouterr()

    rc = main(["inspect", _only_key(capsys)[:12]])
    assert rc == 0
    out = capsys.readouterr().out
    assert "input  : not stored" in out


def test_export_emits_jsonl_for_dataset_entries_and_skips_others(capsys):
    import json

    common = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(
        common
        + [
            "--prompt",
            "STDOUT theanswer",
            "--context",
            "ctx",
            "--system-prompt",
            "terse",
            "--persist",
            "dataset",
        ]
    )
    run_cli(common + ["--prompt", "STDOUT other", "--persist", "cache"])  # no input stored
    capsys.readouterr()

    rc = main(["export"])
    captured = capsys.readouterr()
    assert rc == 0
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1  # only the dataset entry carries an input
    record = json.loads(lines[0])
    assert record["input"] == {"context": "ctx", "prompt": "STDOUT theanswer", "system": "terse"}
    assert "theanswer" in record["output"]["stdout"]
    assert record["client"] == "fake" and record["model"] == "m1"
    # the cache-only entry is reported as skipped, never silently dropped
    assert "skipped 1" in captured.err


def test_export_filters_by_include_and_exclude_tags(capsys):
    import json

    common = [
        "run",
        "--client",
        "fake",
        "--model",
        "m1",
        "--effort",
        "high",
        "--persist",
        "dataset",
    ]
    run_cli(common + ["--prompt", "STDOUT a", "--tag", "keep"])
    run_cli(common + ["--prompt", "STDOUT b", "--tag", "drop"])
    capsys.readouterr()

    main(["export", "--tag", "keep"])
    recs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(recs) == 1 and recs[0]["tags"] == ["keep"]

    main(["export", "--exclude-tag", "drop"])
    recs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(recs) == 1 and recs[0]["tags"] == ["keep"]


def test_export_writes_to_output_file(tmp_path, capsys):
    import json

    common = [
        "run",
        "--client",
        "fake",
        "--model",
        "m1",
        "--effort",
        "high",
        "--persist",
        "dataset",
    ]
    run_cli(common + ["--prompt", "STDOUT a"])
    capsys.readouterr()

    out_file = tmp_path / "corpus.jsonl"
    rc = main(["export", "--output", str(out_file)])
    captured = capsys.readouterr()
    assert rc == 0
    records = [
        json.loads(line)
        for line in out_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert captured.out == ""  # nothing on stdout when writing a file
    assert f"exported 1 record(s) to {out_file}" in captured.err


def test_dataset_hit_backfills_input_then_exports(capsys):
    import json

    common = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(common + ["--prompt", "STDOUT hi", "--context", "ctx"])  # cache: output only
    # same input at dataset depth: a hit that back-fills the input onto the entry
    run_cli(common + ["--prompt", "STDOUT hi", "--context", "ctx", "--persist", "dataset"])
    capsys.readouterr()

    main(["export"])
    recs = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(recs) == 1  # the (now-)dataset entry is exportable
    assert recs[0]["input"] == {"context": "ctx", "prompt": "STDOUT hi"}


def test_export_empty_when_no_dataset_entries(capsys):
    common = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]
    run_cli(common + ["--prompt", "STDOUT a", "--persist", "cache"])
    capsys.readouterr()

    rc = main(["export"])
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.strip() == ""
    assert "exported 0 record(s)" in captured.err
    assert "skipped 1" in captured.err
