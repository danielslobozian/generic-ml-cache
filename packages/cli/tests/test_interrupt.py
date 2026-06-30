# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Graceful stop on signal (0.0.8): a stop signal from the caller (the workflow
engine) tears down the client and records nothing -- an interrupted call is not a
result. POSIX signal/process-group semantics; the cross-process trigger is a real
OS signal, so the deep test is guarded off Windows."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

import pytest
from generic_ml_cache_adapters.adapter.out.client.cli_runtime import wire_cli_client
from generic_ml_cache_adapters.adapter.out.workspace.filesystem_workspace import FilesystemWorkspace
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.run.managed_local_request import (
    ManagedLocalRequest,
)
from generic_ml_cache_core.common.errors import RunInterrupted

import generic_ml_cache_cli.controllers.run as run_ctrl
from generic_ml_cache_cli import cli


class _SleepAdapter:
    """A client that just sleeps far longer than the test -- so the only way the
    call ends in time is by being stopped."""

    name = "sleeper"
    default_executable = "/bin/sh"
    execution_kind = ExecutionKind.LOCAL_MANAGED

    def __init__(self, executable_override=None, timeout=None, stream_path=None):
        wire_cli_client(self, executable_override, timeout, stream_path)

    def prepare(self, run_dir: Path, context: str, prompt: str, system_prompt: str) -> None:
        pass

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
        return [executable, "-c", "sleep 30"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal / process-group semantics")
def test_managed_run_stops_on_signal_and_records_nothing():
    # fire one stop signal once the child is comfortably running
    def interrupt_soon() -> None:
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGINT)

    watcher = threading.Thread(target=interrupt_soon)
    watcher.start()

    fs = FilesystemWorkspace()
    workspace = fs.create()
    start = time.monotonic()
    try:
        with pytest.raises(RunInterrupted):
            _SleepAdapter().execute_managed(
                ManagedLocalRequest(model="m", effort="e", context="context", prompt="prompt"),
                workspace,
            )
    finally:
        fs.dispose(workspace)
    elapsed = time.monotonic() - start

    watcher.join()
    # the run stopped promptly -- it did not wait out the 30s sleep
    assert elapsed < 25


def test_cli_run_maps_interruption_to_a_distinct_exit_code(monkeypatch):
    """A stop is not a failure: the CLI returns 130, separate from miss (3) /
    error (4). The use case raised before any record, so nothing is stored."""

    class _RaisingService:
        def execute(self, command):
            raise RunInterrupted("client run was stopped before it completed")

    class _Wired:
        run_ml = _RaisingService()

    monkeypatch.setattr(run_ctrl, "build_use_cases", lambda *args, **kwargs: _Wired())
    code = cli.main(["run", "--client", "fake", "--model", "m", "--prompt", "STDOUT hi"])
    assert code == 130
