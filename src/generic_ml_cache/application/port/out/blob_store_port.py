# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""BlobStorePort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class BlobStorePort(ABC):
    """Outbound port for storing and retrieving opaque execution output bytes.

    The store is intentionally dumb: it translates a key to its own address and
    reads/writes bytes. It never parses a payload, never computes a key, and
    never interprets content. This is what makes it swappable (filesystem, S3,
    in-memory) without touching the core.

    The key is always produced by CallIdentity.generate_key().
    """

    @abstractmethod
    def get(self, key: str) -> Optional[bytes]:
        """Return the stored bytes for ``key``, or None if not present."""

    @abstractmethod
    def put(self, key: str, output: bytes) -> None:
        """Persist ``output`` under ``key``, overwriting any prior value."""
