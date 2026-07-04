# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""BlobStorePort."""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey


class BlobStorePort(ABC):
    """Outbound port for storing and retrieving opaque execution output bytes.

    The store is intentionally dumb: it translates a key to its own address and
    reads/writes bytes. It never parses a payload, never computes a key, and
    never interprets content. This is what makes it swappable (filesystem, S3,
    in-memory) without touching the core.

    The key is always produced by CallIdentity.generate_key().
    """

    @abstractmethod
    def get(self, key: BlobKey) -> bytes | None:
        """Return the stored bytes for ``key``, or None if not present."""

    @abstractmethod
    def put(self, key: BlobKey, output: bytes) -> None:
        """Persist ``output`` under ``key``, overwriting any prior value."""

    @abstractmethod
    def exists(self, key: BlobKey) -> bool:
        """Return whether a blob is stored under ``key``.

        A cheap, keyless presence test: it fetches no bytes and performs no
        decryption. The DB-first write path uses it to LINK an already-stored
        content-addressed blob (mark it STORED without rewriting) instead of
        putting identical bytes again."""

    @abstractmethod
    def is_healthy(self) -> bool:
        """Return whether the store can actually accept a write RIGHT NOW.

        An ACTIVE canary write, not a passive ping: write a tiny unique probe and
        report whether it landed — which catches a store that is unreachable, out of
        credentials, or read-only (a passive check would miss these). Used to
        fail-fast a DATASET run before an expensive client call it could not persist
        (S1.1). It is an optimization, not a guarantee: storage can drop between the
        probe and the real write, so the persist path must still handle failure
        (TOCTOU)."""

    @abstractmethod
    def remove(self, key: BlobKey) -> None:
        """Delete the bytes stored under ``key``; a no-op if nothing is stored.

        Removal is driven by a reference-counted prune (a blob is content-
        addressed and may be shared by many executions), so a caller removes a
        key only after confirming no execution still references it.
        """
