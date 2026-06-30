# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Robustness: a timeout surfaces cleanly rather than as an uncaught error.

(Store-write atomicity is now covered by tests/test_filesystem_blob_store.py.)
"""

from __future__ import annotations

import subprocess

import generic_ml_cache_cli.controllers.run as run_ctrl
from generic_ml_cache_cli import cli


def test_cli_maps_timeout_to_124(monkeypatch):
    class _TimingOutService:
        def execute(self, command):
            raise subprocess.TimeoutExpired(cmd="client", timeout=0.5)

    class _Wired:
        run_ml = _TimingOutService()

    monkeypatch.setattr(run_ctrl, "build_use_cases", lambda *args, **kwargs: _Wired())
    code = cli.main(
        ["run", "--client", "fake", "--model", "m", "--prompt", "STDOUT hi", "--timeout", "0.5"]
    )
    assert code == 124
