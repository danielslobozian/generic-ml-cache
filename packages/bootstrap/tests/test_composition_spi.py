# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The documented composition entry point is implementable from the stable core surface.

Extends the core W21 annotation walk (``packages/core/tests/test_public_api.py``) to the
bootstrap composition SPI (X17): ``build_application_api`` — its injection params, its
``build_runners`` callback, and the ``PersistenceBackend`` bundle — must reference only
core types that are exported from ``generic_ml_cache_core.__all__``, or the documented
embedding path cannot be implemented without importing unstable internal paths.
"""

from __future__ import annotations

import typing

import generic_ml_cache_core as core

from generic_ml_cache_bootstrap.application import BuildRunners, build_application_api
from generic_ml_cache_bootstrap.persistence_backend import PersistenceBackend


def _core_leaf_types(annotation: object):
    """Yield every class defined in generic_ml_cache_core reachable from an annotation."""
    for arg in typing.get_args(annotation):
        if isinstance(arg, list):  # a Callable's positional-argument list
            for element in arg:
                yield from _core_leaf_types(element)
        else:
            yield from _core_leaf_types(arg)
    if isinstance(annotation, type) and annotation.__module__.startswith("generic_ml_cache_core"):
        yield annotation


def _safe_type_hints(obj: object) -> dict[str, object]:
    try:
        return typing.get_type_hints(obj)
    except Exception:  # noqa: BLE001 — an unresolvable annotation just isn't walked
        return {}


def _visit_core_type(core_type: type, seen: set[type]) -> None:
    """Add ``core_type`` and, transitively, every core type reachable from its fields."""
    if core_type in seen:
        return
    seen.add(core_type)
    for hint in _safe_type_hints(core_type).values():
        for leaf in _core_leaf_types(hint):
            _visit_core_type(leaf, seen)


def _walk(annotation: object, seen: set[type]) -> None:
    for leaf in _core_leaf_types(annotation):
        _visit_core_type(leaf, seen)


def test_build_application_api_references_only_exported_core_types() -> None:
    seen: set[type] = set()
    # The entry point's INJECTION params — what an embedder must supply. The return
    # type (ApplicationApi) is excluded: its inbound use-case ports are CONSUMED through
    # the bundle's fields, not implemented, so — like the core W21 walk — they need not
    # be exported.
    hints = _safe_type_hints(build_application_api)
    for name, hint in hints.items():
        if name == "return":
            continue
        _walk(hint, seen)
    # the build_runners callback's argument + return types (Callable[[...], ...])
    for hint in typing.get_args(BuildRunners):
        _walk(hint, seen)
    # the injectable PersistenceBackend bundle's fields
    for hint in _safe_type_hints(PersistenceBackend).values():
        _walk(hint, seen)

    missing = sorted({t.__name__ for t in seen if t.__name__ not in core.__all__})
    assert missing == [], f"composition SPI references core types absent from __all__: {missing}"
