# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemBlobStore: opaque artifact bytes addressed by content key on disk."""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path

from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort

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
        return self._root / key

    def get(self, key: str) -> bytes | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        return path.read_bytes()

    def put(self, key: str, output: bytes) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path_for(key)
        temp_descriptor, temp_name = tempfile.mkstemp(dir=self._root, suffix=".tmp")
        temp_path = Path(temp_name)
        try:
            with os.fdopen(temp_descriptor, "wb") as temp_file:
                temp_file.write(output)
            os.replace(temp_path, path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

    def remove(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)

    def is_healthy(self) -> bool:
        # Active canary: write a unique probe into a health folder under the blob
        # root and remove it. If the write lands, real writes almost certainly work
        # (this catches an unreachable / read-only / out-of-space store a passive
        # check would miss). Content-addressed name = always new, no collisions.
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
