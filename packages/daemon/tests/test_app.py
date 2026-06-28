# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the application factory."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI

from generic_ml_cache_daemon.app import create_app


def test_create_app_returns_fastapi_instance(tmp_path: Path) -> None:
    application = create_app(tmp_path)
    assert isinstance(application, FastAPI)


def test_create_app_stores_wired_use_cases(tmp_path: Path) -> None:
    application = create_app(tmp_path)
    assert application.state.wired is not None


def test_create_app_stores_session_id(tmp_path: Path) -> None:
    application = create_app(tmp_path, session_id="abc123")
    assert application.state.session_id == "abc123"


def test_create_app_session_id_defaults_to_none(tmp_path: Path) -> None:
    application = create_app(tmp_path)
    assert application.state.session_id is None


def test_create_app_metrics_disabled_by_default(tmp_path: Path) -> None:
    application = create_app(tmp_path)
    assert application.state.enable_metrics is False


def test_create_app_metrics_can_be_enabled(tmp_path: Path) -> None:
    application = create_app(tmp_path, enable_metrics=True)
    assert application.state.enable_metrics is True


def test_create_app_stores_store_root(tmp_path: Path) -> None:
    application = create_app(tmp_path)
    assert application.state.store_root == tmp_path


def test_create_app_starts_without_token(tmp_path: Path) -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GMLCACHE_TOKEN", None)
        application = create_app(tmp_path)
    assert isinstance(application, FastAPI)


def test_create_app_reads_token_from_environment(tmp_path: Path) -> None:
    # create_app must not raise when GMLCACHE_TOKEN is set but the store is
    # not yet encrypted (the token is simply unused against a plain store).
    with patch.dict(os.environ, {"GMLCACHE_TOKEN": "dummy-token-for-wiring-test"}):
        application = create_app(tmp_path)
    assert isinstance(application, FastAPI)
