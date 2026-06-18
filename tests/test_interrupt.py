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
from typing import List

import pytest

from generic_ml_cache import cli
from generic_ml_cache.adapters.base import ClientAdapter
from generic_ml_cache.errors import RunInterrupted
from generic_ml_cache.isolation import record_real_call


class _SleepAdapter(ClientAdapter):
    """A client that just sleeps far longer than the test -- so the only way the
    call ends in time is by being stopped."""

    name = "sleeper"
    default_executable = "/bin/sh"

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
    ) -> List[str]:
        return [executable, "-c", "sleep 30"]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signal / process-group semantics")
def test_record_real_call_stops_on_signal_and_records_nothing():
    # fire one stop signal once the child is comfortably running
    def interrupt_soon() -> None:
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGINT)

    watcher = threading.Thread(target=interrupt_soon)
    watcher.start()

    start = time.monotonic()
    with pytest.raises(RunInterrupted):
        record_real_call(_SleepAdapter(), "/bin/sh", "m", "e", "context", "prompt")
    elapsed = time.monotonic() - start

    watcher.join()
    # the run stopped promptly -- it did not wait out the 30s sleep
    assert elapsed < 25


def test_cli_run_maps_interruption_to_a_distinct_exit_code(monkeypatch):
    """A stop is not a failure: the CLI returns 130, separate from miss (3) /
    error (4), and -- because resolve raised before any save -- nothing is stored."""

    def _raise_interrupted(*_args, **_kwargs):
        raise RunInterrupted("client run was stopped before it completed")

    monkeypatch.setattr(cli, "resolve", _raise_interrupted)
    code = cli.main(["run", "--client", "fake", "--model", "m", "--prompt", "STDOUT hi"])
    assert code == 130
