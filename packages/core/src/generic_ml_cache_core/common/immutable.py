# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Deep-immutability helpers for frozen value/command/identity objects.

A ``@dataclass(frozen=True)`` only freezes its *attribute bindings*; a ``list`` /
``dict`` / ``set`` field is still mutable in place, so the object is only shallowly
immutable — a soundness hole for a cache identity or a command that is keyed on and
forwarded. ``deep_freeze`` normalizes a value (recursively) into immutable
equivalents at the construction boundary; ``thaw`` is its inverse view, producing a
plain, JSON-serializable structure for the rare spot that must serialize a frozen
body (``MappingProxyType`` is not ``json``-serializable, tuples already are).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any, cast


def deep_freeze(value: Any) -> Any:
    """Recursively convert mutable containers into immutable equivalents:
    ``Mapping`` → ``MappingProxyType``, ``list``/``tuple`` → ``tuple``,
    ``set``/``frozenset`` → ``frozenset``. Scalars pass through. Idempotent."""
    if isinstance(value, Mapping):
        mapping_value = cast("Mapping[object, object]", value)
        return MappingProxyType({key: deep_freeze(item) for key, item in mapping_value.items()})
    if isinstance(value, (list, tuple)):
        sequence_value = cast("Iterable[object]", value)
        return tuple(deep_freeze(item) for item in sequence_value)
    if isinstance(value, (set, frozenset)):
        set_value = cast("Iterable[object]", value)
        return frozenset(deep_freeze(item) for item in set_value)
    return value


def thaw(value: Any) -> Any:
    """Inverse view of :func:`deep_freeze` for serialization: ``Mapping`` → ``dict``,
    ``tuple`` → ``list``, ``frozenset`` → ``list``, recursively — a plain structure
    ``json.dumps`` accepts. Scalars pass through."""
    if isinstance(value, Mapping):
        mapping_value = cast("Mapping[object, object]", value)
        return {key: thaw(item) for key, item in mapping_value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        collection_value = cast("Iterable[object]", value)
        return [thaw(item) for item in collection_value]
    return value
