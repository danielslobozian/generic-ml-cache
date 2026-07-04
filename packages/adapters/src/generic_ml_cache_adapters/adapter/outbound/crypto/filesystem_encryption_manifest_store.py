# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemEncryptionManifestStore: the manifest as one JSON file in the store.

Stdlib only (``json`` + ``base64``) — it carries no secrets and must work without
the optional ``[encryption]`` extra, so a public store can be recognised as public
without the crypto library installed.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)
from generic_ml_cache_core.application.port.outbound.encryption_manifest_store_port import (
    EncryptionManifestStorePort,
)

_FILENAME = "encryption.json"


class FilesystemEncryptionManifestStore(EncryptionManifestStorePort):
    """Reads/writes ``<store>/encryption.json``. Its presence == encrypted store."""

    def __init__(self, store_root: Path) -> None:
        self._path = Path(store_root) / _FILENAME

    def load(self) -> EncryptionManifest | None:
        if not self._path.is_file():
            return None
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return EncryptionManifest(
            kdf_salt=base64.b64decode(data["kdf_salt"]),
            wrapped_data_key=base64.b64decode(data["wrapped_data_key"]),
            version=int(data["version"]),
        )

    def save(self, manifest: EncryptionManifest) -> None:
        payload = {
            "version": manifest.version,
            "kdf_salt": base64.b64encode(manifest.kdf_salt).decode("ascii"),
            "wrapped_data_key": base64.b64encode(manifest.wrapped_data_key).decode("ascii"),
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: a partial manifest must never be observable — this file's
        # presence is the encrypted/public commit point.
        tmp = self._path.with_name(_FILENAME + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def delete(self) -> None:
        self._path.unlink(missing_ok=True)
