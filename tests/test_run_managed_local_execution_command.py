# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunManagedLocalExecutionCommand."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.cache_mode import CacheMode
from generic_ml_cache.application.usecase.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)


def _command(**overrides) -> RunManagedLocalExecutionCommand:
    base = dict(client="claude", model="sonnet", effort="high", context="ctx", prompt="do it")
    base.update(overrides)
    return RunManagedLocalExecutionCommand(**base)


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


# --- cacheability query ------------------------------------------------------


def test_plain_call_is_cacheable():
    assert _command().is_uncacheable is False


def test_allow_paths_make_it_uncacheable():
    assert _command(allow_paths=["/workspace"]).is_uncacheable is True


def test_scan_trust_makes_allow_paths_cacheable_again():
    assert _command(allow_paths=["/workspace"], scan_trust=True).is_uncacheable is False


# --- persistence policy query ------------------------------------------------


def test_success_persists_by_default():
    assert _command().should_persist(succeeded=True) is True


def test_failure_does_not_persist_by_default():
    assert _command().should_persist(succeeded=False) is False


def test_failure_persists_with_record_on_error():
    assert _command(record_on_error=True).should_persist(succeeded=False) is True


def test_persist_output_false_never_persists():
    assert _command(persist_output=False).should_persist(succeeded=True) is False
    assert _command(persist_output=False, record_on_error=True).should_persist(succeeded=False) is False
