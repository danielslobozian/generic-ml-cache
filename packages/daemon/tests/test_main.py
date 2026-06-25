# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the __main__ entry point."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


def test_main_calls_uvicorn_run_with_defaults(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    monkeypatch.delenv("GMLCACHE_SESSION", raising=False)
    monkeypatch.delenv("GMLCACHE_METRICS", raising=False)

    mock_run = MagicMock()
    with patch("uvicorn.run", mock_run):
        from generic_ml_cache_daemon.__main__ import main

        main()

    assert mock_run.called
    _, kwargs = mock_run.call_args
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8765


def test_main_passes_session_id_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    monkeypatch.setenv("GMLCACHE_SESSION", "test-session-id")
    monkeypatch.delenv("GMLCACHE_METRICS", raising=False)

    mock_run = MagicMock()
    with patch("uvicorn.run", mock_run):
        from generic_ml_cache_daemon.__main__ import main

        main()

    application_arg = mock_run.call_args[0][0]
    assert application_arg.state.session_id == "test-session-id"


def test_main_enables_metrics_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GMLCACHE_STORE", str(tmp_path))
    monkeypatch.delenv("GMLCACHE_SESSION", raising=False)
    monkeypatch.setenv("GMLCACHE_METRICS", "true")

    mock_run = MagicMock()
    with patch("uvicorn.run", mock_run):
        from generic_ml_cache_daemon.__main__ import main

        main()

    application_arg = mock_run.call_args[0][0]
    assert application_arg.state.enable_metrics is True
