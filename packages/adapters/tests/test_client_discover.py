# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for adapter.out.client.discover — probe and list-models functions."""

from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock

import pytest
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort

from generic_ml_cache_adapters.adapter.out.client.discover import (
    _probe_version,
    list_models,
    list_models_all,
    probe,
    probe_all,
)


class RecordingDiag(DiagnosticsPort):
    """Captures log calls for assertion."""

    def __init__(self) -> None:
        self.events: list = []

    def debug(self, msg: str, **context: object) -> None:
        self.events.append(("debug", msg, context))

    def info(self, msg: str, **context: object) -> None:
        self.events.append(("info", msg, context))

    def warn(self, msg: str, **context: object) -> None:
        self.events.append(("warn", msg, context))

    def error(self, msg: str, exc: Optional[BaseException] = None, **context: object) -> None:
        self.events.append(("error", msg, context))

    def msgs(self) -> list:
        return [e[1] for e in self.events]


# --- _probe_version -----------------------------------------------------------


def test_probe_version_success(monkeypatch) -> None:
    mock_proc = MagicMock()
    mock_proc.stdout = "claude 1.0.0\n"
    mock_proc.stderr = ""
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        lambda *a, **kw: mock_proc,
    )
    version, detail = _probe_version(["claude", "--version"], timeout=5.0)
    assert version == "claude 1.0.0"
    assert detail is None


def test_probe_version_no_output_yields_none_version(monkeypatch) -> None:
    mock_proc = MagicMock()
    mock_proc.stdout = ""
    mock_proc.stderr = ""
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        lambda *a, **kw: mock_proc,
    )
    version, detail = _probe_version(["claude", "--version"], timeout=5.0)
    assert version is None
    assert detail == "no version output"


def test_probe_version_launch_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        MagicMock(side_effect=FileNotFoundError("not found")),
    )
    diag = RecordingDiag()
    version, detail = _probe_version(["nonexistent", "--version"], timeout=5.0, diag=diag)
    assert version is None
    assert detail is not None and "version check failed" in detail
    assert "probe-version FAILED — treating as unknown" in diag.msgs()


def test_probe_version_logs_enter_exit(monkeypatch) -> None:
    mock_proc = MagicMock()
    mock_proc.stdout = "v1\n"
    mock_proc.stderr = ""
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        lambda *a, **kw: mock_proc,
    )
    diag = RecordingDiag()
    _probe_version(["claude", "--version"], timeout=5.0, diag=diag)
    assert "probe-version ENTER" in diag.msgs()
    assert "probe-version EXIT" in diag.msgs()


# --- probe -------------------------------------------------------------------


def test_probe_client_not_found_returns_not_present() -> None:
    result = probe("claude", executable="/no/such/path/claude")
    assert result.present is False
    assert result.name == "claude"


def test_probe_client_not_found_logs_exit(monkeypatch) -> None:
    diag = RecordingDiag()
    result = probe("claude", executable="/no/such/dir/claude-bin", diag=diag)
    assert result.present is False
    assert "probe ENTER" in diag.msgs()
    assert "probe EXIT" in diag.msgs()


def test_probe_found_client_logs_enter_exit(monkeypatch) -> None:
    mock_proc = MagicMock()
    mock_proc.stdout = "version 2\n"
    mock_proc.stderr = ""
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        lambda *a, **kw: mock_proc,
    )
    # Use "sh" — guaranteed to exist everywhere; patch resolve_executable to succeed
    import shutil

    sh_path = shutil.which("sh")
    if sh_path is None:
        pytest.skip("sh not on PATH")

    diag = RecordingDiag()
    result = probe("claude", executable=sh_path, diag=diag)
    assert result.present is True
    assert "probe ENTER" in diag.msgs()
    assert "probe EXIT" in diag.msgs()


# --- probe_all ---------------------------------------------------------------


def test_probe_all_returns_list_for_each_registered_client(monkeypatch) -> None:
    mock_proc = MagicMock()
    mock_proc.stdout = "v1\n"
    mock_proc.stderr = ""
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        lambda *a, **kw: mock_proc,
    )
    diag = RecordingDiag()
    results = probe_all(whitelist=frozenset(["claude"]), diag=diag)
    assert isinstance(results, list)
    assert "probe-all ENTER" in diag.msgs()
    assert "probe-all EXIT" in diag.msgs()


# --- list_models -------------------------------------------------------------


def test_list_models_client_not_found_returns_not_present() -> None:
    result = list_models("claude", executable="/no/such/path/claude")
    assert result.present is False
    assert result.name == "claude"


def test_list_models_client_not_found_logs_exit() -> None:
    diag = RecordingDiag()
    result = list_models("claude", executable="/no/such/dir/claude-bin", diag=diag)
    assert result.present is False
    assert "list-models ENTER" in diag.msgs()
    assert "list-models EXIT" in diag.msgs()


def test_list_models_no_models_argv_client(monkeypatch) -> None:
    """Clients whose models_argv returns None report unsupported."""
    import shutil

    sh_path = shutil.which("sh")
    if sh_path is None:
        pytest.skip("sh not on PATH")

    diag = RecordingDiag()
    # claude adapter returns None for models_argv
    result = list_models("claude", executable=sh_path, diag=diag)
    assert result.present is True
    assert result.supported is False
    assert "list-models ENTER" in diag.msgs()
    assert "list-models EXIT" in diag.msgs()


def test_list_models_launch_failure(monkeypatch) -> None:
    """subprocess failure on a client that has models_argv."""
    import shutil

    sh_path = shutil.which("sh")
    if sh_path is None:
        pytest.skip("sh not on PATH")

    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        MagicMock(side_effect=OSError("exec failed")),
    )
    diag = RecordingDiag()
    # cursor adapter returns a non-None models_argv, so subprocess is reached
    result = list_models("cursor", executable=sh_path, diag=diag)
    assert result.present is True
    assert "model listing failed" in (result.reason or "")
    assert "list-models launch failed" in diag.msgs()
    assert "list-models EXIT" in diag.msgs()


def test_list_models_nonzero_returncode(monkeypatch) -> None:
    import shutil

    sh_path = shutil.which("sh")
    if sh_path is None:
        pytest.skip("sh not on PATH")

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stdout = ""
    mock_proc.stderr = "auth required"
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        lambda *a, **kw: mock_proc,
    )
    diag = RecordingDiag()
    result = list_models("cursor", executable=sh_path, diag=diag)
    assert result.present is True
    assert result.supported is True
    assert "list-models EXIT" in diag.msgs()


def test_list_models_success(monkeypatch) -> None:
    import shutil

    sh_path = shutil.which("sh")
    if sh_path is None:
        pytest.skip("sh not on PATH")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = ""
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        lambda *a, **kw: mock_proc,
    )
    diag = RecordingDiag()
    result = list_models("cursor", executable=sh_path, diag=diag)
    assert result.present is True
    assert "list-models EXIT" in diag.msgs()


def test_list_models_unknown_client_raises() -> None:
    from generic_ml_cache_core.common.errors import UnknownClient

    with pytest.raises(UnknownClient):
        list_models("nonexistent-client-xyz")


# --- list_models_all ---------------------------------------------------------


def test_list_models_all_returns_list(monkeypatch) -> None:
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = ""
    monkeypatch.setattr(
        "generic_ml_cache_adapters.adapter.out.client.discover.subprocess.run",
        lambda *a, **kw: mock_proc,
    )
    diag = RecordingDiag()
    results = list_models_all(whitelist=frozenset(["claude"]), diag=diag)
    assert isinstance(results, list)
    assert "list-models-all ENTER" in diag.msgs()
    assert "list-models-all EXIT" in diag.msgs()
