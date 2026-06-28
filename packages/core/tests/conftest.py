# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared test fixtures for the core package (pure domain/port/use-case tests)."""

from __future__ import annotations

import base64

import pytest


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "no-such-config.ini"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    for var in ("GMLCACHE_MODE", "GMLCACHE_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)


def write_directive(relpath: str, content: str) -> str:
    """Build a WRITE directive line for the fake client."""
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return f"WRITE {relpath} {b64}"
