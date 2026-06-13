# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Allow-path: declared scan folders, passthrough by default (0.0.5)."""

from __future__ import annotations

import pytest

from generic_ml_cache import CacheMiss, Mode, Request, get_adapter, resolve
from generic_ml_cache.prime_directive import build_system_prompt


def _req(prompt="STDOUT hi", **kw):
    return Request(client="fake", model="m", effort="", context="ctx", prompt=prompt, **kw)


# --- folders are never keyed -----------------------------------------------


def test_allow_path_not_in_key():
    a = Request("fake", "m", "", context="c", prompt="p", allow_paths=["/some/folder"])
    b = Request("fake", "m", "", context="c", prompt="p")
    assert a.input_data == b.input_data  # folders never enter the key


def test_requires_passthrough_flag():
    assert _req(allow_paths=["/x"]).requires_passthrough
    assert not _req().requires_passthrough


# --- door + add-dir wiring --------------------------------------------------


def test_allowed_read_paths_merges_files_and_folders_sorted():
    r = Request(
        "fake",
        "m",
        "",
        context="",
        prompt="p",
        input_files={"/a/file.txt": "sha"},
        allow_paths=["/z/folder", "/a/folder"],
    )
    assert r.allowed_read_paths == ["/a/file.txt", "/a/folder", "/z/folder"]
    assert r.add_dir_paths == ["/a/folder", "/z/folder"]  # folders only


def test_directive_lists_folders():
    sp = build_system_prompt(None, allowed_read_paths=["/data/repo"])
    assert "/data/repo" in sp and "DECLARED READ PATHS" in sp


def test_claude_emits_add_dir():
    assert get_adapter("claude").read_access_argv(["/x", "/y"]) == [
        "--add-dir",
        "/x",
        "--add-dir",
        "/y",
    ]


def test_other_adapters_have_no_hard_read_access():
    # codex/cursor deferred to 0.0.8; fake is directive-only
    assert get_adapter("fake").read_access_argv(["/x"]) == []
    assert get_adapter("codex").read_access_argv(["/x"]) == []
    assert get_adapter("cursor").read_access_argv(["/x"]) == []


# --- passthrough behaviour --------------------------------------------------


def test_allow_path_is_passthrough(store, tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    out = resolve(_req(allow_paths=[str(folder)]), store, mode=Mode.CACHE)
    assert out.passthrough and not out.hit and not out.recorded
    assert len(store) == 0  # stored nothing


def test_allow_path_offline_errors(store, tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    with pytest.raises(CacheMiss):
        resolve(_req(allow_paths=[str(folder)]), store, mode=Mode.OFFLINE)


def test_trust_scan_makes_it_cacheable(store, tmp_path):
    folder = tmp_path / "src"
    folder.mkdir()
    req = _req(allow_paths=[str(folder)])
    out = resolve(req, store, mode=Mode.CACHE, trust_scan=True)
    assert out.recorded and not out.passthrough and len(store) == 1
    # and now a hit is served
    again = resolve(req, store, mode=Mode.OFFLINE, trust_scan=True)
    assert again.hit


# --- CLI ergonomics ---------------------------------------------------------


def test_cli_allow_path_must_be_directory(tmp_path):
    from generic_ml_cache.cli import main

    f = tmp_path / "not_a_dir.txt"
    f.write_text("x")
    with pytest.raises(SystemExit):
        main(
            [
                "run",
                "--client",
                "fake",
                "--model",
                "m",
                "--prompt",
                "STDOUT hi",
                "--allow-path",
                str(f),  # a file, not a directory
            ]
        )
