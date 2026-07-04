# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The declared public API (``__all__``) is real and importable (V20)."""

from __future__ import annotations

import generic_ml_cache_core as core


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
