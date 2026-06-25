# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared test fixtures for daemon route tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from generic_ml_cache_daemon.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """A TestClient wired against a real but temporary store."""
    application = create_app(tmp_path)
    return TestClient(application)
