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

    widths = {len(line) for line in render_banner(color=False).splitlines()}
    assert len(widths) == 1  # all three box lines are the same width


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
    assert "record · replay · check · tokens" in out
    assert "usage:" in out


def test_bare_invocation_has_no_ansi_when_not_a_tty(capsys):
    main([])
    # capsys stdout is not a terminal, so the banner must be plain text
    assert "\x1b[" not in capsys.readouterr().out


def test_help_flag_shows_the_banner(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["-h"])
    assert excinfo.value.code == 0
    assert "record · replay · check · tokens" in capsys.readouterr().out


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
