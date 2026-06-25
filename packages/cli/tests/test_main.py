# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the package entry point (__main__.py)."""

from __future__ import annotations

import runpy

import pytest


def test_package_entrypoint_exits_with_main_return_code(monkeypatch):
    monkeypatch.setattr("generic_ml_cache_cli.cli.main", lambda: 0)
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("generic_ml_cache_cli", run_name="__main__")
    assert exc_info.value.code == 0
