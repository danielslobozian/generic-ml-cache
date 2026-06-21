# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for Message."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.message import Message


def test_carries_role_and_content():
    message = Message(role="user", content="hello")
    assert message.role == "user"
    assert message.content == "hello"


def test_is_frozen():
    message = Message(role="user", content="hello")
    with pytest.raises(Exception):
        message.content = "changed"  # type: ignore[misc]
