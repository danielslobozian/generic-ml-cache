# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for FilesystemWorkspace — the temp-folder workspace lifecycle.

Core owns the decision to isolate a run; this adapter is the mechanism. The diff
between a pre-run snapshot and the post-run folder is how generated files are
detected without the client declaring them.
"""

from __future__ import annotations

from generic_ml_cache_adapters.adapter.out.workspace.filesystem_workspace import FilesystemWorkspace


def test_create_makes_two_distinct_existing_directories():
    ws = FilesystemWorkspace().create()
    try:
        assert ws.run_dir.is_dir()
        assert ws.config_home.is_dir()
        assert ws.run_dir != ws.config_home
    finally:
        FilesystemWorkspace().dispose(ws)


def test_capture_detects_a_newly_created_file():
    workspace = FilesystemWorkspace()
    ws = workspace.create()
    try:
        baseline = workspace.snapshot(ws.run_dir)
        (ws.run_dir / "out.txt").write_bytes(b"hello")
        files = workspace.capture(ws.run_dir, baseline)
        assert [f.name for f in files] == ["out.txt"]
        assert files[0].content == b"hello"
    finally:
        workspace.dispose(ws)


def test_capture_detects_a_modified_file_but_not_an_unchanged_one():
    workspace = FilesystemWorkspace()
    ws = workspace.create()
    try:
        (ws.run_dir / "keep.txt").write_bytes(b"original")
        (ws.run_dir / "change.txt").write_bytes(b"before")
        baseline = workspace.snapshot(ws.run_dir)  # both files are now baseline
        (ws.run_dir / "change.txt").write_bytes(b"after")  # only this one changes
        files = workspace.capture(ws.run_dir, baseline)
        assert [f.name for f in files] == ["change.txt"]
        assert files[0].content == b"after"
    finally:
        workspace.dispose(ws)


def test_capture_is_empty_when_nothing_changed():
    workspace = FilesystemWorkspace()
    ws = workspace.create()
    try:
        (ws.run_dir / "seed.txt").write_bytes(b"x")
        baseline = workspace.snapshot(ws.run_dir)
        assert workspace.capture(ws.run_dir, baseline) == []
    finally:
        workspace.dispose(ws)


def test_dispose_removes_both_directories():
    workspace = FilesystemWorkspace()
    ws = workspace.create()
    workspace.dispose(ws)
    assert not ws.run_dir.exists()
    assert not ws.config_home.exists()


def test_dispose_is_idempotent():
    workspace = FilesystemWorkspace()
    ws = workspace.create()
    workspace.dispose(ws)
    workspace.dispose(ws)  # second call must not raise
    assert not ws.run_dir.exists()
