# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the deep-immutability helpers (deep_freeze / thaw)."""

from __future__ import annotations

from types import MappingProxyType

from generic_ml_cache_core.common.immutable import deep_freeze, thaw


def test_deep_freeze_converts_nested_containers():
    frozen = deep_freeze({"a": [1, {"b": 2}], "c": {"d", "e"}})
    assert isinstance(frozen, MappingProxyType)
    assert isinstance(frozen["a"], tuple)
    assert isinstance(frozen["a"][1], MappingProxyType)
    assert isinstance(frozen["c"], frozenset)


def test_deep_freeze_leaves_scalars_untouched():
    assert deep_freeze("text") == "text"
    assert deep_freeze(42) == 42
    assert deep_freeze(None) is None


def test_deep_freeze_is_idempotent():
    once = deep_freeze({"a": [1, 2]})
    twice = deep_freeze(once)
    assert twice == once
    assert isinstance(twice["a"], tuple)


def test_thaw_produces_plain_json_serializable_structures():
    frozen = deep_freeze({"a": [1, {"b": 2}], "c": {"e"}})
    plain = thaw(frozen)
    assert plain == {"a": [1, {"b": 2}], "c": ["e"]}
    assert isinstance(plain, dict)
    assert isinstance(plain["a"], list)
    assert isinstance(plain["a"][1], dict)


def test_thaw_round_trips_through_json():
    import json

    frozen = deep_freeze({"model": "x", "messages": [{"role": "user"}], "stop": ["a", "b"]})
    # MappingProxyType is not json-serializable directly; thaw makes it so.
    assert json.loads(json.dumps(thaw(frozen))) == {
        "model": "x",
        "messages": [{"role": "user"}],
        "stop": ["a", "b"],
    }
