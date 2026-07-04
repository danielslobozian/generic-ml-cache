# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""BlobStorePort."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BlobStorePort(ABC):
    """Outbound port for storing and retrieving opaque execution output bytes.

    The store is intentionally dumb: it translates a key to its own address and
    reads/writes bytes. It never parses a payload, never computes a key, and
    never interprets content. This is what makes it swappable (filesystem, S3,
    in-memory) without touching the core.

    The key is always produced by CallIdentity.generate_key().
    """

    @abstractmethod
    def get(self, key: str) -> bytes | None:
        """Return the stored bytes for ``key``, or None if not present."""

    @abstractmethod
    def put(self, key: str, output: bytes) -> None:
        """Persist ``output`` under ``key``, overwriting any prior value."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether a blob is stored under ``key``.

        A cheap, keyless presence test: it fetches no bytes and performs no
        decryption. The DB-first write path uses it to LINK an already-stored
        content-addressed blob (mark it STORED without rewriting) instead of
        putting identical bytes again."""

    @abstractmethod
    def remove(self, key: str) -> None:
        """Delete the bytes stored under ``key``; a no-op if nothing is stored.

        Removal is driven by a reference-counted prune (a blob is content-
        addressed and may be shared by many executions), so a caller removes a
        key only after confirming no execution still references it.
        """
