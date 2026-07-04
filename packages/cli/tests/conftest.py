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

import pytest
from generic_ml_cache_adapters.adapter.outbound.api.stub_api_client_adapter import (
    StubApiClientAdapter,
)
from generic_ml_cache_adapters.adapter.outbound.client.cli_runtime import wire_cli_client
from generic_ml_cache_adapters.adapter.outbound.client.composed_local_client import (
    ComposedLocalClient,
)
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind

from generic_ml_cache_cli.discovery import register

FAKE_SCRIPT = str(Path(__file__).with_name("fake_client.py"))


class FakeAdapter(ComposedLocalClient):
    name = "fake"
    # An absolute path with a separator -> resolve_executable uses it verbatim.
    default_executable = sys.executable
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(self, executable_override=None, timeout=None, stream_path=None):
        wire_cli_client(self, executable_override, timeout, stream_path)

    @classmethod
    def descriptor(cls):
        return AdapterDescriptor.local_cli("fake", (), "Fake")

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
    ) -> list[str]:
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


class _FakeApiAdapter(StubApiClientAdapter):
    name = "fake-api"

    @classmethod
    def descriptor(cls):
        return AdapterDescriptor.api("fake-api", (), "Fake API")


@pytest.fixture(autouse=True, scope="session")
def _register_fake_adapter():
    for cls in (FakeAdapter, FakeStdinAdapter, _FakeApiAdapter):
        register(cls)


class FakeStdinAdapter(ComposedLocalClient):
    """Like FakeAdapter, but delivers the prompt on stdin (as the real adapters
    now do) so the launcher's stdin path can be exercised end-to-end -- including
    a prompt far larger than any OS argv-size limit."""

    name = "fake_stdin"
    default_executable = sys.executable
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(self, executable_override=None, timeout=None, stream_path=None):
        wire_cli_client(self, executable_override, timeout, stream_path)

    @classmethod
    def descriptor(cls):
        return AdapterDescriptor.local_cli("fake_stdin", (), "Fake (stdin)")

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
    ) -> list[str]:
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
    store) into tmp via the standard XDG/Windows base-dir vars, and clear
    the env layers -- so no test reads the real user config or writes into the
    real store."""
    monkeypatch.setenv("GMLCACHE_CONFIG", str(tmp_path / "no-such-config.ini"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    for var in (
        "GMLCACHE_MODE",
        "GMLCACHE_PERSIST",
        "GMLCACHE_TIMEOUT",
        "GMLCACHE_TOKEN",
        "GMLCACHE_SESSION",
    ):
        monkeypatch.delenv(var, raising=False)


def write_directive(relpath: str, content: str) -> str:
    """Build a WRITE directive line for the fake client."""
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return f"WRITE {relpath} {b64}"
