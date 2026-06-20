# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared test fixtures.

Registers a ``fake`` client adapter that launches ``fake_client.py`` via the
current Python interpreter, so the whole cache can be exercised on Linux, macOS
and Windows with no real CLI installed.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path
from typing import List

import pytest

from generic_ml_cache import register
from generic_ml_cache.application.port.out.base import ClientAdapter
from generic_ml_cache.adapter.out.storage.store import CassetteStore

FAKE_SCRIPT = str(Path(__file__).with_name("fake_client.py"))


class FakeAdapter(ClientAdapter):
    name = "fake"
    # An absolute path with a separator -> resolve_executable uses it verbatim.
    default_executable = sys.executable

    def prepare(self, run_dir, context, prompt, system_prompt) -> None:
        (run_dir / "_in_context.txt").write_text(context, encoding="utf-8")
        (run_dir / "_in_prompt.txt").write_text(prompt, encoding="utf-8")
        (run_dir / "_in_system.txt").write_text(system_prompt, encoding="utf-8")

    def build_argv(
        self,
        executable,
        run_dir,
        model,
        effort,
        context,
        prompt,
        system_prompt,
        client_args=(),
        grants=(),
    ) -> List[str]:
        return [
            executable,
            FAKE_SCRIPT,
            "--model",
            model,
            "--effort",
            effort,
            "--context-file",
            str(run_dir / "_in_context.txt"),
            "--prompt-file",
            str(run_dir / "_in_prompt.txt"),
            "--system-file",
            str(run_dir / "_in_system.txt"),
        ]


@pytest.fixture(autouse=True, scope="session")
def _register_fake_adapter():
    register(FakeAdapter())
    register(FakeStdinAdapter())


class FakeStdinAdapter(ClientAdapter):
    """Like FakeAdapter, but delivers the prompt on stdin (as the real adapters
    now do) so the launcher's stdin path can be exercised end-to-end -- including
    a prompt far larger than any OS argv-size limit."""

    name = "fake_stdin"
    default_executable = sys.executable

    def prepare(self, run_dir, context, prompt, system_prompt) -> None:
        (run_dir / "_in_context.txt").write_text(context, encoding="utf-8")
        (run_dir / "_in_system.txt").write_text(system_prompt, encoding="utf-8")

    def build_argv(
        self,
        executable,
        run_dir,
        model,
        effort,
        context,
        prompt,
        system_prompt,
        client_args=(),
        grants=(),
    ) -> List[str]:
        return [
            executable,
            FAKE_SCRIPT,
            "--model",
            model,
            "--effort",
            effort,
            "--context-file",
            str(run_dir / "_in_context.txt"),
            "--system-file",
            str(run_dir / "_in_system.txt"),
            "--prompt-stdin",
        ]

    def stdin_payload(self, context, prompt, system_prompt):
        return prompt


@pytest.fixture(autouse=True)
def _isolate_config(monkeypatch, tmp_path):
    """Isolate config *and* store from the real machine: point config discovery at
    a guaranteed-absent file, send the per-user data dir (and thus the default
    cassette store) into tmp via the standard XDG/Windows base-dir vars, and clear
    the env layers -- so no test reads the real user config or writes into the
    real store."""
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "no-such-config.ini"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    for var in ("GMLCACHE_MODE", "GMLCACHE_TIMEOUT"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def store(tmp_path) -> CassetteStore:
    return CassetteStore(tmp_path / "cassettes")


def write_directive(relpath: str, content: str) -> str:
    """Build a WRITE directive line for the fake client."""
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return f"WRITE {relpath} {b64}"
