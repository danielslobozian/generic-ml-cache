# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemBlobStore: opaque artifact bytes addressed by content key on disk."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort


class FilesystemBlobStore(BlobStorePort):
    """A directory of content-addressed blobs, one file per key.

    Dumb by construction: it stores and returns opaque bytes by key and never
    parses, computes a key, or interprets content. Writes are atomic (a unique
    temp file in the same directory, then ``os.replace``), so a crash mid-write
    never leaves a half-written blob.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def _path_for(self, key: str) -> Path:
        return self._root / key

    def get(self, key: str) -> Optional[bytes]:
        path = self._path_for(key)
        if not path.exists():
            return None
        return path.read_bytes()

    def put(self, key: str, output: bytes) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path_for(key)
        temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            temp_path.write_bytes(output)
            os.replace(temp_path, path)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

    def remove(self, key: str) -> None:
        self._path_for(key).unlink(missing_ok=True)
