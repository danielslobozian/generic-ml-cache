# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunMlExecutionCommand."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)


def _managed(**overrides) -> RunMlExecutionCommand:
    base = dict(
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        client="claude",
        model="sonnet",
        effort="high",
        context="ctx",
        prompt="do it",
    )
    base.update(overrides)
    return RunMlExecutionCommand(**base)


def _api(**overrides) -> RunMlExecutionCommand:
    base = dict(execution_kind=ExecutionKind.API, client="openai", model="gpt-x")
    base.update(overrides)
    return RunMlExecutionCommand(**base)


# --- construction ------------------------------------------------------------


def test_required_fields_managed():
    command = _managed()
    assert command.execution_kind is ExecutionKind.LOCAL_MANAGED
    assert command.client == "claude"
    assert command.prompt == "do it"


def test_required_fields_api():
    command = _api()
    assert command.execution_kind is ExecutionKind.API
    assert command.client == "openai"


def test_defaults():
    command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.LOCAL_MANAGED, client="claude", model="m"
    )
    assert command.effort == ""
    assert command.context == ""
    assert command.prompt == ""
    assert command.user_system_prompt is None
    assert command.input_file_paths == ()
    assert command.allow_paths == ()
    assert command.scan_trust is False
    assert command.client_args == ()
    assert command.grants == ()
    assert command.cache_mode is CacheMode.CACHE
    assert command.persistence_depth is PersistenceDepth.CACHE
    assert command.record_on_error is False
    assert command.tags == ()
    assert command.session_id is None


def test_is_frozen():
    command = _managed()
    with pytest.raises(FrozenInstanceError):
        command.prompt = "other"  # type: ignore[misc]


def test_carries_raw_paths_not_fingerprints():
    command = _managed(input_file_paths=["/src/a.py", "/src/b.py"])
    assert command.input_file_paths == ("/src/a.py", "/src/b.py")


# --- cacheability (managed) --------------------------------------------------


def test_managed_plain_call_is_cacheable():
    assert _managed().is_uncacheable is False


def test_managed_allow_paths_make_it_uncacheable():
    assert _managed(allow_paths=["/workspace"]).is_uncacheable is True


def test_managed_scan_trust_makes_allow_paths_cacheable_again():
    assert _managed(allow_paths=["/workspace"], scan_trust=True).is_uncacheable is False


# --- cacheability (api) -------------------------------------------------------


def test_api_is_always_cacheable():
    assert _api().is_uncacheable is False
    assert _api(allow_paths=["/workspace"]).is_uncacheable is False


# --- persistence policy -------------------------------------------------------


def test_success_persists_by_default():
    assert _managed().should_persist(succeeded=True) is True


def test_failure_does_not_persist_by_default():
    assert _managed().should_persist(succeeded=False) is False


def test_failure_persists_with_record_on_error():
    assert _managed(record_on_error=True).should_persist(succeeded=False) is True


def test_meter_depth_never_persists():
    assert _managed(persistence_depth=PersistenceDepth.METER).should_persist(True) is False
    assert _managed(persistence_depth=PersistenceDepth.METER).should_persist(False) is False


def test_api_failure_does_not_persist_by_default():
    assert _api().should_persist(succeeded=False) is False
