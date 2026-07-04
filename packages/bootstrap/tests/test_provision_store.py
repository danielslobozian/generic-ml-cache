# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the C-2 persistence-contract handshake (``provision_store``)."""

from __future__ import annotations

import pytest
from generic_ml_cache_core.application.port.outbound.store_migration_port import (
    CURRENT_MODEL_VERSION,
    StoreMigrationPort,
)
from generic_ml_cache_core.common.errors import PersistenceContractOutdated

from generic_ml_cache_bootstrap.application import provision_store


class _FakeMigration(StoreMigrationPort):
    def __init__(self, version: int) -> None:
        self._version = version
        self.migrated = False

    def implemented_version(self) -> int:
        return self._version

    def migrate_to_current(self) -> None:
        self.migrated = True


def test_migrates_when_adapter_is_current() -> None:
    migration = _FakeMigration(CURRENT_MODEL_VERSION)
    provision_store(migration)
    assert migration.migrated is True


def test_migrates_when_adapter_is_ahead() -> None:
    # An adapter that implements a newer contract than this build still serves.
    migration = _FakeMigration(CURRENT_MODEL_VERSION + 1)
    provision_store(migration)
    assert migration.migrated is True


def test_refuses_and_does_not_migrate_when_adapter_is_behind() -> None:
    migration = _FakeMigration(CURRENT_MODEL_VERSION - 1)
    with pytest.raises(PersistenceContractOutdated):
        provision_store(migration)
    assert migration.migrated is False
