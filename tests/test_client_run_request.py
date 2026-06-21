# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ClientRunRequest."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.client_run_request import ClientRunRequest


def test_required_fields():
    client_run_request = ClientRunRequest(
        client="claude",
        model="sonnet",
        effort="high",
        context="some context",
        prompt="do the thing",
    )
    assert client_run_request.client == "claude"
    assert client_run_request.model == "sonnet"
    assert client_run_request.effort == "high"
    assert client_run_request.context == "some context"
    assert client_run_request.prompt == "do the thing"


def test_optional_fields_default():
    client_run_request = ClientRunRequest(client="claude", model="m", effort="", context="", prompt="")
    assert client_run_request.allow_paths == []
    assert client_run_request.client_args == []
    assert client_run_request.grants == frozenset()
    assert client_run_request.user_system_prompt is None


def test_allow_paths_are_present():
    client_run_request = ClientRunRequest(
        client="claude",
        model="m",
        effort="",
        context="",
        prompt="",
        allow_paths=["/workspace/repo"],
    )
    assert "/workspace/repo" in client_run_request.allow_paths


def test_grants_are_a_frozenset():
    client_run_request = ClientRunRequest(
        client="claude",
        model="m",
        effort="",
        context="",
        prompt="",
        grants=frozenset({"net", "read"}),
    )
    assert isinstance(client_run_request.grants, frozenset)
    assert "net" in client_run_request.grants


def test_cache_policy_fields_are_absent():
    assert not hasattr(ClientRunRequest, "cache_mode")
    assert not hasattr(ClientRunRequest, "persist_output")
    assert not hasattr(ClientRunRequest, "scan_trust")


def test_is_frozen():
    client_run_request = ClientRunRequest(client="claude", model="m", effort="", context="", prompt="")
    with pytest.raises(Exception):
        client_run_request.client = "codex"  # type: ignore[misc]
