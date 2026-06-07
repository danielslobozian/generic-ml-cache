# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import os


from generic_ml_cache.cli import main
from conftest import write_directive


def run_cli(args):
    return main(args)


def test_cli_records_then_replays_offline(tmp_path, capsys):
    store = str(tmp_path / "cas")
    common = [
        "run",
        "--client",
        "fake",
        "--model",
        "m1",
        "--effort",
        "high",
        "--store",
        store,
        "--output-dir",
        str(tmp_path / "out"),
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
            "--store",
            str(tmp_path / "cas"),
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
            "--store",
            str(tmp_path / "cas"),
            "--output-dir",
            str(tmp_path / "out"),
            "--prompt",
            "EXIT 5",
        ]
    )
    assert rc == 5


def test_cli_writes_files_to_output_dir(tmp_path):
    outdir = tmp_path / "out"
    rc = run_cli(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--store",
            str(tmp_path / "cas"),
            "--output-dir",
            str(outdir),
            "--prompt",
            write_directive("deep/file.txt", "data\n"),
        ]
    )
    assert rc == 0
    assert (outdir / "deep" / "file.txt").read_text(encoding="utf-8") == "data\n"


def test_cli_inspect(tmp_path, capsys):
    store = tmp_path / "cas"
    run_cli(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--store",
            str(store),
            "--output-dir",
            str(tmp_path / "out"),
            "--prompt",
            write_directive("r.txt", "hi\n"),
        ]
    )
    cassette_path = next(store.glob("*.json"))
    rc = run_cli(["inspect", str(cassette_path)])
    assert rc == 0
    report = capsys.readouterr().out
    assert "client : fake" in report
    assert "r.txt" in report


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
