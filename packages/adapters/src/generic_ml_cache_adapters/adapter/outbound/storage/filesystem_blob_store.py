# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemBlobStore: opaque artifact bytes addressed by an execution-owned key on disk."""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path

from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.common.errors import StoreUnavailable

#: Sub-directory under the blob root for canary-write health probes. Probe files
#: get always-new names (a fresh random token, named by its own hash) and are
#: removed right after writing, so the folder stays empty and is never mistaken for
#: a blob.
_HEALTH_DIR = ".health"


class FilesystemBlobStore(BlobStorePort):
    """A directory of blobs, one file per key.

    Dumb by construction: it stores and returns opaque bytes by key and never
    parses, computes a key, or interprets content. Writes are atomic (a fresh
    temp file minted per write in the same directory, then ``os.replace``), so a
    crash mid-write never leaves a half-written blob and a concurrent write of the
    same key never shares one scratch file.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _path_for(self, key: str) -> Path:
        # Re-validate the key through the core value object at the adapter boundary
        # (X16): a raw traversal string like "../outside" can masquerade as a BlobKey
        # (Python does no runtime type check), and this is a PUBLIC, installable
        # adapter an embedder calls directly — so force the key through BlobKey's own
        # constructor, which rejects anything that could escape the root, before
        # resolving ``root / key``. The value object IS the guard (no bespoke
        # path-check here — that misplaced security is what W7 declined).
        return self._root / BlobKey(key)

    def get(self, key: str) -> bytes | None:
        path = self._path_for(key)  # BlobKey ValueError (X16 traversal guard) escapes as-is
        if not path.exists():
            return None
        # An existing-but-unreadable blob (permissions, transient IO, a directory where
        # a file is expected, a Windows lock) raises a raw OSError; translate it at the
        # adapter boundary (Y5/§10) so a driver never sees a foreign type — absent still
        # returns None (→ ArtifactBlobMissing in core), a real IO fault is StoreUnavailable.
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StoreUnavailable(f"blob store read failed for {key!r}: {exc}") from exc

    def put(self, key: str, output: bytes) -> None:
        path = self._path_for(key)  # validate the key before any filesystem side effect
        # Translate any backend IO failure (unwritable root, full disk, replace onto a
        # bad target) to StoreUnavailable (Y5/§10); the inner guard still unlinks the
        # scratch file and re-raises a non-OSError (e.g. KeyboardInterrupt) untranslated.
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            temp_descriptor, temp_name = tempfile.mkstemp(dir=self._root, suffix=".tmp")
            temp_path = Path(temp_name)
            try:
                with os.fdopen(temp_descriptor, "wb") as temp_file:
                    temp_file.write(output)
                os.replace(temp_path, path)
            except BaseException:
                temp_path.unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise StoreUnavailable(f"blob store write failed for {key!r}: {exc}") from exc

    def remove(self, key: str) -> None:
        try:
            self._path_for(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StoreUnavailable(f"blob store remove failed for {key!r}: {exc}") from exc

    def is_healthy(self) -> bool:
        # Active canary: write a unique probe into a health folder under the blob
        # root and remove it. If the write lands, real writes almost certainly work
        # (this catches an unreachable / read-only / out-of-space store a passive
        # check would miss). The probe name is a fresh-token hash — always new.
        try:
            health_dir = self._root / _HEALTH_DIR
            health_dir.mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex.encode()
            probe_path = health_dir / hashlib.sha256(token).hexdigest()
            probe_path.write_bytes(token)
            probe_path.unlink(missing_ok=True)
            return True
        except OSError:
            return False
