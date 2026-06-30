# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ExecutionQueryService (the execution-query inbound capability)."""

from generic_ml_cache_core.application.port.inbound.execution_query.find_current_execution_command import (
    FindCurrentExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_executions_by_key_prefix_command import (
    FindExecutionsByKeyPrefixCommand,
)
from generic_ml_cache_core.application.port.inbound.execution_query.tags_for_execution_command import (
    TagsForExecutionCommand,
)
from generic_ml_cache_core.application.usecase.execution_query_service import ExecutionQueryService


class _FakeRepo:
    def current_execution_summaries(self):
        return ["summary-a", "summary-b"]

    def total_stored_bytes(self):
        return 4096

    def tags_for(self, execution_key):
        return ["alpha", "beta"] if execution_key == "k1" else []

    def find_current(self, execution_key):
        return "execution" if execution_key == "k1" else None

    def find_current_by_key_prefix(self, key_prefix):
        return ["e1", "e2"] if key_prefix == "ab" else []


def _service():
    return ExecutionQueryService(_FakeRepo())  # type: ignore[arg-type]  # duck-typed repo


def test_list_summaries_delegates():
    assert _service().list_summaries() == ["summary-a", "summary-b"]


def test_total_stored_bytes_delegates():
    assert _service().total_stored_bytes() == 4096


def test_tags_for_delegates():
    assert _service().tags_for(TagsForExecutionCommand("k1")) == ["alpha", "beta"]
    assert _service().tags_for(TagsForExecutionCommand("missing")) == []


def test_find_current_delegates():
    assert _service().find_current(FindCurrentExecutionCommand("k1")) == "execution"
    assert _service().find_current(FindCurrentExecutionCommand("missing")) is None


def test_find_by_key_prefix_delegates():
    assert _service().find_by_key_prefix(FindExecutionsByKeyPrefixCommand("ab")) == ["e1", "e2"]
    assert _service().find_by_key_prefix(FindExecutionsByKeyPrefixCommand("zz")) == []
