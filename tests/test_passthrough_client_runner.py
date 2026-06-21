# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for PassthroughClientRunner — runs the opaque native args directly.

The fake client resolves to the Python interpreter, so passing native args like
``-c '<code>'`` exercises a real subprocess launch on every OS.
"""

from __future__ import annotations

from generic_ml_cache.adapter.out.client.passthrough_client_runner import (
    PassthroughClientRunner,
)
from generic_ml_cache.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache.application.port.out.passthrough_runner_port import PassthroughRunnerPort


def test_is_a_passthrough_runner_port():
    assert isinstance(PassthroughClientRunner(), PassthroughRunnerPort)


def test_forwards_native_args_and_captures_stdout():
    result = PassthroughClientRunner().run("fake", ["-c", "print('passthrough out')"])
    assert isinstance(result, ClientRunResult)
    assert result.stdout.strip() == "passthrough out"
    assert result.exit_code == 0


def test_captures_stderr():
    result = PassthroughClientRunner().run("fake", ["-c", "import sys; sys.stderr.write('warn')"])
    assert result.stderr == "warn"


def test_captures_a_nonzero_exit():
    result = PassthroughClientRunner().run("fake", ["-c", "import sys; sys.exit(2)"])
    assert result.exit_code == 2


def test_never_captures_files(tmp_path, monkeypatch):
    # Passthrough runs in the caller's cwd (no isolation), so the client really
    # writes the file there — but we capture nothing.
    monkeypatch.chdir(tmp_path)
    result = PassthroughClientRunner().run("fake", ["-c", "open('x.txt','w').write('y')"])
    assert result.files == []
    assert (tmp_path / "x.txt").read_text() == "y"  # the client did write it
