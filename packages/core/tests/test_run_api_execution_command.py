# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for RunApiExecutionCommand."""

from __future__ import annotations

import pytest

from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.domain.model.run.message import Message
from generic_ml_cache_core.application.port.inbound.run_api_execution_command import (
    RunApiExecutionCommand,
)


def test_defaults():
    command = RunApiExecutionCommand(provider="openai", model="gpt-x")
    assert command.messages == []
    assert command.cache_mode is CacheMode.CACHE
    assert command.persistence_depth is PersistenceDepth.CACHE
    assert command.record_on_error is False


def test_carries_messages():
    command = RunApiExecutionCommand(
        provider="openai", model="gpt-x", messages=[Message(role="user", content="hi")]
    )
    assert command.messages[0].content == "hi"


def test_should_persist_policy():
    assert RunApiExecutionCommand(provider="p", model="m").should_persist(True) is True
    assert RunApiExecutionCommand(provider="p", model="m").should_persist(False) is False
    assert (
        RunApiExecutionCommand(provider="p", model="m", record_on_error=True).should_persist(False)
        is True
    )
    assert (
        RunApiExecutionCommand(
            provider="p", model="m", persistence_depth=PersistenceDepth.METER
        ).should_persist(True)
        is False
    )


def test_has_no_local_client_fields():
    assert not hasattr(RunApiExecutionCommand, "input_file_paths")
    assert not hasattr(RunApiExecutionCommand, "allow_paths")
    assert not hasattr(RunApiExecutionCommand, "grants")


def test_is_frozen():
    command = RunApiExecutionCommand(provider="openai", model="gpt-x")
    with pytest.raises(Exception):
        command.model = "other"  # type: ignore[misc]
