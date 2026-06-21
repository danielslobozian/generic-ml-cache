# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for fingerprint_messages."""

from __future__ import annotations

from generic_ml_cache.application.domain.model.message import Message
from generic_ml_cache.application.domain.service.message_fingerprinting import fingerprint_messages


def _user(content: str) -> Message:
    return Message(role="user", content=content)


def test_is_deterministic():
    messages = [_user("a"), _user("b")]
    assert fingerprint_messages(messages) == fingerprint_messages(messages)


def test_is_order_sensitive():
    first = fingerprint_messages([_user("a"), _user("b")])
    second = fingerprint_messages([_user("b"), _user("a")])
    assert first != second


def test_role_matters():
    first = fingerprint_messages([Message(role="user", content="x")])
    second = fingerprint_messages([Message(role="system", content="x")])
    assert first != second


def test_content_matters():
    assert fingerprint_messages([_user("a")]) != fingerprint_messages([_user("b")])


def test_empty_messages_have_a_stable_fingerprint():
    assert fingerprint_messages([]) == fingerprint_messages([])
    assert len(fingerprint_messages([])) == 64
