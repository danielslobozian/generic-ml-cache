# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for AbstractPassthroughLocalAdapter — runs opaque native args directly."""

from __future__ import annotations

from generic_ml_cache_core.adapter.out.client.abstract_passthrough_local_adapter import (
    AbstractPassthroughLocalAdapter,
)
from generic_ml_cache_core.adapter.registry import get_adapter
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort


def _runner() -> AbstractPassthroughLocalAdapter:
    """Return a fresh passthrough runner wrapping the registered fake adapter."""
    return AbstractPassthroughLocalAdapter(get_adapter("fake"))


def test_is_an_ml_runner_port():
    assert isinstance(_runner(), MlRunnerPort)


def test_forwards_native_args_and_captures_stdout():
    result = _runner().run(
        MlRequest(
            model="",
            effort="",
            context="",
            prompt="",
            native_args=["-c", "print('passthrough out')"],
        )
    )
    assert isinstance(result, ClientRunResult)
    assert result.stdout.strip() == "passthrough out"
    assert result.exit_code == 0


def test_captures_stderr():
    result = _runner().run(
        MlRequest(
            model="",
            effort="",
            context="",
            prompt="",
            native_args=["-c", "import sys; sys.stderr.write('warn')"],
        )
    )
    assert result.stderr == "warn"


def test_captures_a_nonzero_exit():
    result = _runner().run(
        MlRequest(
            model="",
            effort="",
            context="",
            prompt="",
            native_args=["-c", "import sys; sys.exit(2)"],
        )
    )
    assert result.exit_code == 2


def test_never_captures_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = _runner().run(
        MlRequest(
            model="",
            effort="",
            context="",
            prompt="",
            native_args=["-c", "open('x.txt','w').write('y')"],
        )
    )
    assert result.files == []
    assert (tmp_path / "x.txt").read_text() == "y"
