# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The declared public API (``__all__``) is real and importable (V20)."""

from __future__ import annotations

import inspect
import typing

import generic_ml_cache_core as core


def _core_leaf_types(annotation: object):
    """Yield every class defined in generic_ml_cache_core reachable from a type
    annotation (unwrapping Optional/list/tuple/Mapping/Union/… to their leaves)."""
    for arg in typing.get_args(annotation):
        yield from _core_leaf_types(arg)
    if isinstance(annotation, type) and annotation.__module__.startswith("generic_ml_cache_core"):
        yield annotation


def _safe_type_hints(obj: object) -> dict[str, object]:
    try:
        return typing.get_type_hints(obj)
    except Exception:  # noqa: BLE001 — an unresolvable annotation just isn't walked
        return {}


def _visit_core_type(t: type, seen: set[type]) -> None:
    """Add ``t`` and, transitively, every core type reachable from its fields."""
    if t in seen:
        return
    seen.add(t)
    for hint in _safe_type_hints(t).values():
        for leaf in _core_leaf_types(hint):
            _visit_core_type(leaf, seen)


def _referenced_core_types(port: type) -> set[type]:
    """The transitive closure of core types an embedder needs to implement ``port``:
    the leaf types in its method signatures, plus the fields of every core DTO those
    reach — so ``MlExecution`` drags in ``Artifact`` / ``TokenUsage`` / ``ExecutionState`` …"""
    seen: set[type] = set()
    for name, method in inspect.getmembers(port, predicate=inspect.isfunction):
        if name.startswith("__"):
            continue
        for hint in _safe_type_hints(method).values():
            for leaf in _core_leaf_types(hint):
                _visit_core_type(leaf, seen)
    return seen


def test_every_all_symbol_is_importable() -> None:
    # A missing import behind an __all__ entry (or a renamed symbol) is a broken
    # public contract — this catches it. Guards the injectable-SPI surface embedders
    # implement (the outbound ports) as well as ApplicationApi + the command.
    missing = [name for name in core.__all__ if not hasattr(core, name)]
    assert missing == []


def test_the_injectable_spi_ports_are_exported() -> None:
    # V33 invites embedders to implement these to run on their own store — they must
    # be part of the declared public API, not undeclared internals.
    for name in (
        "SaveMlRunPort",
        "ReadMlRunPort",
        "PurgeMlRunsPort",
        "RepairMlRunsPort",
        "RecordCallEventPort",
        "StoreMigrationPort",
        "BlobStorePort",
        "AdapterCatalogPort",
        "ApplicationApi",
    ):
        assert name in core.__all__
        assert hasattr(core, name)


# The composition-SPI port the build_runners callback CONSUMES: a driver receives an
# instance of it and immediately widens the result to RegisteredAdapterPort for the
# runner dict, so it never names the method return types (LocalClientPort → the whole
# local-client role-port hierarchy). It is exported (X17) so the callback's signature
# can be written from the package root, but it is checked for import (below), not for
# full implementer-closure — the default resolver is framework-provided; a rare custom
# one imports the driven-client ports directly.
_CONSUMED_SPI_PORTS = frozenset({"AdapterResolverPort"})


def test_the_consumed_composition_spi_ports_are_importable() -> None:
    for name in _CONSUMED_SPI_PORTS:
        assert name in core.__all__ and hasattr(core, name)


def test_public_ports_vocabulary_is_fully_exported() -> None:
    # An embedder implementing a public outbound port must be able to construct/read
    # every core type its signatures reference — transitively (W21). If a referenced
    # type is not in __all__, the SPI is not implementable from the stable surface;
    # this walk fails the moment a port grows a signature referencing a fresh type.
    ports = [
        getattr(core, name)
        for name in core.__all__
        if name.endswith("Port") and name not in _CONSUMED_SPI_PORTS
    ]
    missing = sorted(
        {
            t.__name__
            for port in ports
            for t in _referenced_core_types(port)
            if t.__name__ not in core.__all__
        }
    )
    assert missing == [], f"public ports reference core types absent from __all__: {missing}"


def test_structured_errors_are_exported() -> None:
    # Consumers branch on these subclasses (each carries a `code`/`status_code` the
    # drivers map to an exit code or HTTP status), so they must be importable from
    # the public surface, not reached via a private module path (W22).
    for name in (
        "ProviderApiError",
        "ProviderProtocolError",
        "MigrationFailed",
        "UnsupportedExecutionMode",
        "CapabilityUnavailable",
        "PersistenceContractOutdated",
        "StoreUnavailable",
        "StoreCorrupt",
        "StoreConsistencyError",
    ):
        assert name in core.__all__
        assert hasattr(core, name)
