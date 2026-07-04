# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StoreMigrationPort — the whole-store persistence-contract handshake (C-2).

Migration is promoted from a free function to an outbound port so the store's
schema evolution is a first-class, injectable contract. Core owns
``CURRENT_MODEL_VERSION`` — the *contract* version, an opaque integer meaning
"the domain model as of this build", NOT a schema detail. At startup bootstrap
compares the injected adapter's ``implemented_version()`` against it and refuses
to serve if the adapter is behind (``PersistenceContractOutdated``).

Single whole-store version, checked once at boot, fail-fast — the Flyway /
Liquibase / Hibernate-``validate`` model (a unified relational store whose tables
evolve as one lineage), NOT per-object versioning (Avro / ``serialVersionUID``,
which is only for independently serialized/transmitted objects). The blob store is
exempt: opaque bytes have no schema. The handshake is *preventive* — it fails
before serving rather than discovering a stale mapping mid-write, so there is no
check-after-write and no bad-data cleanup.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

#: The model-contract version this build requires the persistence adapter to
#: implement. Bumped whenever a migration changes the persisted domain model
#: (e.g. the C-4 per-artifact status extends it). An adapter reporting a lower
#: ``implemented_version()`` is refused at boot.
CURRENT_MODEL_VERSION = 3


class StoreMigrationPort(ABC):
    """Outbound port for evolving the store to the current model contract."""

    @abstractmethod
    def implemented_version(self) -> int:
        """Return the model-contract version this adapter's code knows how to
        persist — the highest version it can migrate a store up to. Compared at
        boot against ``CURRENT_MODEL_VERSION``; a lower value fails fast."""

    @abstractmethod
    def migrate_to_current(self) -> None:
        """Bring the backing store up to the adapter's implemented version,
        idempotently — a no-op when the store is already current. Safe to call on
        every startup."""
