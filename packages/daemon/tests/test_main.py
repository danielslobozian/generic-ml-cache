# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the __main__ entry point."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from generic_ml_cache_daemon.__main__ import main


def test_help_prints_usage_and_exits_without_starting_server() -> None:
    # Regression: ``main()`` used to ignore argv and boot uvicorn, so ``--help``
    # hung forever (it stalled the release smoke-install for 12 minutes). It must
    # now print usage and exit 0 before any server starts.
    with patch("uvicorn.run") as mock_run, pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert not mock_run.called


def test_module_invocation_help_exits_promptly() -> None:
    # Exactly what the release workflow's smoke-install runs. Must return quickly,
    # not block on a running server.
    result = subprocess.run(
        [sys.executable, "-m", "generic_ml_cache_daemon", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_custom_host_and_port_flags(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    mock_run = MagicMock()
    with patch("uvicorn.run", mock_run):
        main(["--host", "0.0.0.0", "--port", "9999"])
    _, kwargs = mock_run.call_args
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["port"] == 9999


def test_main_parses_size_age_and_adapters_from_env(tmp_path: Path, monkeypatch) -> None:
    # Exercises the GMLCACHE_MAX_SIZE / MAX_AGE / EVICTION_INTERVAL / ADAPTERS parsing.
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    monkeypatch.setenv("GMLCACHE_MAX_SIZE", "10mb")
    monkeypatch.setenv("GMLCACHE_MAX_AGE", "2h")
    monkeypatch.setenv("GMLCACHE_EVICTION_INTERVAL", "120")
    monkeypatch.setenv("GMLCACHE_ADAPTERS", "claude, cursor")

    mock_run = MagicMock()
    with patch("uvicorn.run", mock_run):
        main([])

    application = mock_run.call_args[0][0]
    assert application.state.whitelist == frozenset({"claude", "cursor"})


def test_main_calls_uvicorn_run_with_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    monkeypatch.delenv("GMLCACHE_SESSION", raising=False)
    monkeypatch.delenv("GMLCACHE_METRICS", raising=False)

    mock_run = MagicMock()
    with patch("uvicorn.run", mock_run):
        from generic_ml_cache_daemon.__main__ import main

        main([])

    assert mock_run.called
    _, kwargs = mock_run.call_args
    # X4: the gateway is single-principal (body-only cache key), so it MUST bind
    # localhost by default — never a routable address that could serve one caller's
    # provider-authorized response to another.
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8765


def test_main_passes_session_id_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    monkeypatch.setenv("GMLCACHE_SESSION", "test-session-id")
    monkeypatch.delenv("GMLCACHE_METRICS", raising=False)

    mock_run = MagicMock()
    with patch("uvicorn.run", mock_run):
        from generic_ml_cache_daemon.__main__ import main

        main([])

    application_arg = mock_run.call_args[0][0]
    assert application_arg.state.session_id == "test-session-id"


def test_main_enables_metrics_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    monkeypatch.delenv("GMLCACHE_SESSION", raising=False)
    monkeypatch.setenv("GMLCACHE_METRICS", "true")

    mock_run = MagicMock()
    with patch("uvicorn.run", mock_run):
        from generic_ml_cache_daemon.__main__ import main

        main([])

    application_arg = mock_run.call_args[0][0]
    assert application_arg.state.enable_metrics is True
