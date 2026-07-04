# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""EncryptionManifestStorePort."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)


class EncryptionManifestStorePort(ABC):
    """Outbound port for the store's encryption manifest — the single source of
    truth for whether the store is encrypted.

    The manifest holds only **non-secret** material (salt + wrapped data key); its
    *presence* is what makes a store encrypted. Writing it is the atomic commit
    point of enabling encryption; deleting it is part of disabling / crypto-shred.
    """

    @abstractmethod
    def load(self) -> EncryptionManifest | None:
        """Return the stored manifest, or None when the store is public."""

    @abstractmethod
    def save(self, manifest: EncryptionManifest) -> None:
        """Write the manifest, atomically (it is the commit point of enabling)."""

    @abstractmethod
    def delete(self) -> None:
        """Remove the manifest; a no-op if absent. Returns the store to public."""

    def state(self) -> EncryptionState:
        """Derived state: ENCRYPTED iff a manifest is present, else PUBLIC."""
        return EncryptionState.ENCRYPTED if self.load() is not None else EncryptionState.PUBLIC
