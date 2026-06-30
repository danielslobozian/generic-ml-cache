# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the standalone CLI client adapters + their shared CliRuntime.

Each adapter subclasses ComposedLocalClient and composes a CliRuntime (via
wire_cli_client), supplying only its translation hooks. The base delegates the
LocalClientPort surface to the runtime, so no call logic is duplicated. The
adapter's job is to make the call; the managed-execution use case owns the
workspace and captures artifacts. These
tests exercise the call against the fake client registered in conftest, driving
the workspace lifecycle the way the core use case does.
"""

from __future__ import annotations

import base64

from generic_ml_cache_bootstrap.discovery.composition import get_adapter
from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.run.managed_local_request import (
    ManagedLocalRequest,
)
from generic_ml_cache_core.application.domain.model.run.passthrough_request import (
    PassthroughRequest,
)

from generic_ml_cache_adapters.adapter.out.workspace.filesystem_workspace import FilesystemWorkspace


def _fake_adapter():
    """Return a fresh instance of the registered fake adapter."""
    return type(get_adapter("fake"))()


def _run_managed(adapter, prompt: str):
    """Drive a managed call the way the core use case does: create a workspace,
    stage inputs, snapshot, make the call, capture files, dispose."""
    fs = FilesystemWorkspace()
    workspace = fs.create()
    try:
        request = ManagedLocalRequest(model="m", effort="", context="", prompt=prompt)
        adapter.stage_inputs(request, workspace)
        baseline = fs.snapshot(workspace.run_dir)
        answer = adapter.execute_managed(request, workspace)
        files = fs.capture(workspace.run_dir, baseline)
        return answer, files
    finally:
        fs.dispose(workspace)


# ---------------------------------------------------------------------------
# Managed call — adapter makes the call; the workspace captures artifacts
# ---------------------------------------------------------------------------


def test_execute_managed_returns_an_answer_with_stdout_and_exit():
    answer, _ = _run_managed(_fake_adapter(), "STDOUT hello-from-fake")
    assert isinstance(answer, ClientAnswer)
    assert "hello-from-fake" in answer.stdout
    assert answer.exit_code == 0


def test_execute_managed_surfaces_a_nonzero_exit():
    answer, _ = _run_managed(_fake_adapter(), "EXIT 3")
    assert answer.exit_code == 3


def test_answer_is_files_free_capture_is_the_use_cases_job():
    answer, _ = _run_managed(_fake_adapter(), "STDOUT just-text")
    assert not hasattr(answer, "files")  # a ClientAnswer carries no artifacts


def test_workspace_captures_a_generated_file_after_the_call():
    encoded = base64.b64encode(b"artifact body").decode("ascii")
    _, files = _run_managed(_fake_adapter(), f"WRITE out/made.txt {encoded}")
    produced = [f for f in files if f.name == "out/made.txt"]
    assert len(produced) == 1
    assert produced[0].content == b"artifact body"


def test_no_files_captured_when_the_client_writes_none():
    _, files = _run_managed(_fake_adapter(), "STDOUT nothing-written")
    assert files == []


# ---------------------------------------------------------------------------
# Passthrough call — a raw relay, no workspace, files-free answer
# ---------------------------------------------------------------------------


def test_execute_passthrough_relays_native_args_as_an_answer():
    answer = _fake_adapter().execute_passthrough(
        PassthroughRequest(native_args=["-c", "print('pt-answer')"])
    )
    assert isinstance(answer, ClientAnswer)
    assert answer.stdout.strip() == "pt-answer"
    assert answer.exit_code == 0


def test_execute_passthrough_captures_stderr_and_exit():
    answer = _fake_adapter().execute_passthrough(
        PassthroughRequest(native_args=["-c", "import sys; sys.stderr.write('warn'); sys.exit(2)"])
    )
    assert answer.stderr == "warn"
    assert answer.exit_code == 2


# ---------------------------------------------------------------------------
# Composition surface — ComposedLocalClient delegates the call API to _call
# ---------------------------------------------------------------------------


def test_wired_adapter_exposes_the_call_methods():
    adapter = _fake_adapter()
    for method in (
        "execute_managed",
        "execute_passthrough",
        "stage_inputs",
        "resolve_executable",
        "version_argv",
        "models_argv",
    ):
        assert callable(getattr(adapter, method))
    assert adapter.models_argv("exe") is None  # fake has no model listing
