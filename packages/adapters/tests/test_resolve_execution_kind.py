# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for resolve_execution_kind: client name → ExecutionKind routing."""

from __future__ import annotations

import pytest

from generic_ml_cache_core.adapter.registry import resolve_execution_kind
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.common.errors import UnknownClient


def test_local_managed_adapter_resolves_to_local_managed():
    assert resolve_execution_kind("fake") is ExecutionKind.LOCAL_MANAGED


def test_built_in_local_adapters_resolve_to_local_managed():
    for name in ("claude", "codex", "cursor"):
        assert resolve_execution_kind(name) is ExecutionKind.LOCAL_MANAGED


def test_api_provider_resolves_to_api():
    assert resolve_execution_kind("gemini") is ExecutionKind.API


def test_fake_api_provider_resolves_to_api():
    assert resolve_execution_kind("fake-api") is ExecutionKind.API


def test_unknown_client_raises_unknown_client():
    with pytest.raises(UnknownClient, match="not-a-thing"):
        resolve_execution_kind("not-a-thing")


def test_error_message_lists_known_clients():
    with pytest.raises(UnknownClient) as exc_info:
        resolve_execution_kind("not-a-thing")
    msg = str(exc_info.value)
    assert "fake" in msg
    assert "gemini" in msg
