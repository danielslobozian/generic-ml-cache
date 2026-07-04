# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""BlobKey — a validated blob-store key (C-5, V14)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from generic_ml_cache_core.common.checksum import file_content_fingerprint

if TYPE_CHECKING:
    from generic_ml_cache_core.application.domain.model.execution.execution_id import ExecutionId

# A blob key addresses one entry in the (dumb) blob store, which resolves it as a
# single path component (``root / key``). A real key is ``<execution_id>_<content
# fingerprint>`` — a UUID prefix (hyphens) and a sha-256 hex suffix — so the charset
# permits letters, digits, ``.``, ``_`` and ``-``. This covers every key the system
# produces while excluding anything that could escape the store root: no ``/`` or
# ``\``, no whitespace or control chars, bounded length.
_BLOB_KEY = re.compile(r"[A-Za-z0-9._-]{1,255}")


class BlobKey(str):
    """A blob-store key validated at construction (parse-at-edge, AGENTS §11).

    The traversal defense lives here in the core, NOT in the blob store: the store
    is dumb (``root / str(key)``) and a filesystem-only ``..`` check would be both
    inconsistent (an S3 store cannot traverse) and misplaced (§5 — adapters do not
    hold security logic). Instead the key is made *unconstructible* if unsafe, so a
    key read back from a possibly-corrupted DB row is rejected at the boundary
    before it can ever reach the store.

    It is a ``str`` subclass, so it drops in wherever a key string is used (dict
    lookups, ``root / key``, SQL parameters) — a plain ``str`` is not itself a
    validated key, but every key the system *produces* is built through this type
    (the fingerprint sites and the repository's DB-read edge).
    """

    __slots__ = ()

    def __new__(cls, value: str) -> BlobKey:
        if value in (".", "..") or _BLOB_KEY.fullmatch(value) is None:
            raise ValueError(
                f"invalid blob key {value!r}: a key must be a bounded "
                "[A-Za-z0-9._-] string that cannot escape the store root"
            )
        return super().__new__(cls, value)

    @classmethod
    def for_execution(cls, execution_id: ExecutionId, content_bytes: bytes) -> BlobKey:
        """Mint the key an execution owns for one artifact's content (X25).

        ``<execution_id>_<content fingerprint>``: the ``execution_id`` prefix gives
        the blob a single owner, so deleting the execution deletes exactly its own
        blobs and no two executions ever name the same blob file; the content
        fingerprint suffix distinguishes the several artifacts of one execution. Key
        generation lives here on the value object that owns the format (AGENTS §6),
        not in the store or the use case.
        """
        return cls(f"{execution_id}_{file_content_fingerprint(content_bytes)}")
