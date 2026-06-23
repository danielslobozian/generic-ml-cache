# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunPassthroughExecutionCommand."""

from __future__ import annotations

import pytest

from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.port.inbound.run_passthrough_execution_command import (
    RunPassthroughExecutionCommand,
)


def test_defaults():
    command = RunPassthroughExecutionCommand(client="claude")
    assert command.native_args == []
    assert command.cache_mode is CacheMode.CACHE
    assert command.persistence_depth is PersistenceDepth.CACHE
    assert command.record_on_error is False


def test_carries_opaque_native_args():
    command = RunPassthroughExecutionCommand(client="claude", native_args=["--help", "-x"])
    assert command.native_args == ["--help", "-x"]


def test_success_persists_by_default():
    assert RunPassthroughExecutionCommand(client="c").should_persist(succeeded=True) is True


def test_failure_does_not_persist_by_default():
    assert RunPassthroughExecutionCommand(client="c").should_persist(succeeded=False) is False


def test_failure_persists_with_record_on_error():
    command = RunPassthroughExecutionCommand(client="c", record_on_error=True)
    assert command.should_persist(succeeded=False) is True


def test_meter_depth_never_persists():
    command = RunPassthroughExecutionCommand(client="c", persistence_depth=PersistenceDepth.METER)
    assert command.should_persist(succeeded=True) is False


def test_has_no_scan_or_allow_path_fields():
    assert not hasattr(RunPassthroughExecutionCommand, "allow_paths")
    assert not hasattr(RunPassthroughExecutionCommand, "scan_trust")


def test_is_frozen():
    command = RunPassthroughExecutionCommand(client="claude")
    with pytest.raises(Exception):
        command.client = "codex"  # type: ignore[misc]
