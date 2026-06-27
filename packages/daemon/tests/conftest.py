# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared test fixtures for daemon route tests."""

from __future__ import annotations

from pathlib import Path
from typing import Generator, Tuple

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from generic_ml_cache_daemon.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """A TestClient wired against a real but temporary store."""
    application = create_app(tmp_path)
    with TestClient(application) as tc:
        yield tc


@pytest.fixture
def app_and_client(tmp_path: Path) -> Generator[Tuple[FastAPI, TestClient], None, None]:
    """Return (app, TestClient) so tests can seed wired internals directly."""
    application = create_app(tmp_path)
    with TestClient(application) as tc:
        yield application, tc


def write_directive(path: Path, content: str) -> None:
    """Write a directive file used by fake-adapter tests."""
    path.write_text(content)
