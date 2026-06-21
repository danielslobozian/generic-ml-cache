# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunManagedLocalExecutionCommand."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.cache_mode import CacheMode
from generic_ml_cache.application.usecase.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)


def test_required_fields():
    command = RunManagedLocalExecutionCommand(
        client="claude",
        model="sonnet",
        effort="high",
        context="ctx",
        prompt="do it",
    )
    assert command.client == "claude"
    assert command.prompt == "do it"


def test_defaults():
    command = RunManagedLocalExecutionCommand(
        client="claude", model="m", effort="", context="", prompt="p"
    )
    assert command.user_system_prompt is None
    assert command.input_file_paths == []
    assert command.allow_paths == []
    assert command.scan_trust is False
    assert command.client_args == []
    assert command.grants == []
    assert command.cache_mode is CacheMode.CACHE
    assert command.persist_output is True
    assert command.record_on_error is False


def test_carries_raw_paths_not_fingerprints():
    command = RunManagedLocalExecutionCommand(
        client="claude",
        model="m",
        effort="",
        context="",
        prompt="p",
        input_file_paths=["/src/a.py", "/src/b.py"],
    )
    assert command.input_file_paths == ["/src/a.py", "/src/b.py"]


def test_does_not_expose_fingerprints_or_call_identity():
    assert not hasattr(RunManagedLocalExecutionCommand, "input_fingerprints")
    assert not hasattr(RunManagedLocalExecutionCommand, "call_identity")


def test_is_frozen():
    command = RunManagedLocalExecutionCommand(
        client="claude", model="m", effort="", context="", prompt="p"
    )
    with pytest.raises(Exception):
        command.prompt = "other"  # type: ignore[misc]
