# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os

import pytest

from generic_ml_cache import config
from generic_ml_cache.cli import main
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


def test_cli_inspect(tmp_path, monkeypatch, capsys):
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
            write_directive("r.txt", "hi\n"),
        ]
    )
    cassette_path = next(config.default_store_path().glob("*.json"))
    rc = run_cli(["inspect", str(cassette_path)])
    assert rc == 0
    report = capsys.readouterr().out
    assert "client : fake" in report
    assert "r.txt" in report


def test_inspect_missing_file_is_clean(tmp_path, capsys):
    rc = run_cli(["inspect", str(tmp_path / "does-not-exist.json")])
    assert rc == 4
    err = capsys.readouterr().err
    assert "no such cassette" in err
    assert "Traceback" not in err


def test_inspect_malformed_file_is_clean(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    rc = run_cli(["inspect", str(bad)])
    assert rc == 4
    err = capsys.readouterr().err
    assert "not a valid cassette" in err
    assert "Traceback" not in err


def test_inspect_directory_is_clean(tmp_path, capsys):
    d = tmp_path / "a-directory"
    d.mkdir()
    rc = run_cli(["inspect", str(d)])
    assert rc == 4
    assert "cannot read cassette" in capsys.readouterr().err


# --- cross-platform invariants --------------------------------------------


def test_cassette_uses_posix_paths_on_any_os(tmp_path):
    """Even on Windows, captured paths are stored with forward slashes."""
    from generic_ml_cache import Mode, Request, resolve
    from generic_ml_cache.store import CassetteStore

    store = CassetteStore(tmp_path / "cas")
    req = Request(
        "fake", "m1", "high", "ctx", write_directive(os.path.join("a", "b", "c.txt"), "x\n")
    )
    out = resolve(req, store, mode=Mode.CACHE)
    # fake_client received an OS-native path but the cache normalizes on capture
    assert any("/" in f.path and "\\" not in f.path for f in out.response.files)


def test_multibyte_unicode_roundtrips(tmp_path):
    from generic_ml_cache import Mode, Request, resolve, apply_response
    from generic_ml_cache.store import CassetteStore

    store = CassetteStore(tmp_path / "cas")
    text = "café — 日本語 — \temoji 🚀\n"
    req = Request("fake", "m1", "high", "ctx", write_directive("u.txt", text))
    out = resolve(req, store, mode=Mode.CACHE)
    dest = tmp_path / "out"
    apply_response(out.response, dest)
    assert (dest / "u.txt").read_text(encoding="utf-8") == text


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
    from generic_ml_cache.cli import render_banner

    widths = {len(line) for line in render_banner(color=False).splitlines()}
    assert len(widths) == 1  # all three box lines are the same width


def test_render_banner_color_is_opt_in():
    from generic_ml_cache.cli import render_banner

    assert "\x1b[" not in render_banner(color=False)
    assert "\x1b[" in render_banner(color=True)


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
