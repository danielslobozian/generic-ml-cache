# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StoreEncryptor: crash-safe enable / disable / rotate / invalidate of a store.

Encryption is store-wide and all-or-nothing. Switching it on or off transforms the
blob content (the only place sensitive data lives); the metadata is unaffected.

The migration is crash-safe by construction:

1. Build the transformed blobs in a separate ``blobs.staging/`` — the live
   ``blobs/`` is never touched while staging.
2. Write a **commit marker** (atomic). This is the point of no return.
3. Move each staged blob into place (atomic per file), then flip the manifest.

Recovery (idempotent, runs on every open, needs no token or crypto):

- marker present  -> a commit was interrupted: **roll forward** (finish the moves,
  flip the manifest, clean up).
- marker absent, staging present -> crashed while staging: **roll back** (drop
  staging; the live blobs were never touched).

The migration runs under an EXCLUSIVE store lock; the normal content-write path holds
the SAME lock SHARED (X8), so a write and a migration are mutually excluded — a write
completes first or waits the migration out, and no plaintext blob lands in a store
mid-encryption. (Before X8 only the migration acquired the lock, so a concurrent write
could slip through — the lock was one-sided.)
"""

from __future__ import annotations

import base64
import json
import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)
from generic_ml_cache_core.application.port.outbound.cipher_port import CipherPort
from generic_ml_cache_core.application.port.outbound.encryption_manifest_store_port import (
    EncryptionManifestStorePort,
)
from generic_ml_cache_core.application.port.outbound.store_lock_port import StoreLockPort
from generic_ml_cache_core.common.errors import EncryptionStateError

_BLOBS = "blobs"
_STAGING = "blobs.staging"
_MARKER = "encryption.committing.json"
# files wiped by invalidate (the "format"); the lock file is left (we hold it).
_WIPE_ON_INVALIDATE = ("executions.sqlite3", "registry.sqlite3")


class StoreEncryptor:
    """Enable/disable/rotate/invalidate at-rest encryption of a store directory.

    ``cipher`` is required for enable/disable/rotate; ``recover`` and ``invalidate``
    never touch the cipher, so a store can self-heal and be wiped without the
    optional ``[encryption]`` extra installed.
    """

    def __init__(
        self,
        store_root: Path,
        manifest_store: EncryptionManifestStorePort,
        lock: StoreLockPort,
        cipher: CipherPort | None = None,
    ) -> None:
        self._root = Path(store_root)
        self._blobs = self._root / _BLOBS
        self._staging = self._root / _STAGING
        self._marker = self._root / _MARKER
        self._manifest_store = manifest_store
        self._lock = lock
        self._cipher = cipher

    # -- recovery ---------------------------------------------------------

    def recover(self) -> None:
        """Finish or roll back an interrupted migration. Cheap no-op when there is
        nothing pending (a bare existence check, no lock taken)."""
        if not self._marker.exists() and not self._staging.exists():
            return
        with self._lock.acquire():
            self._recover_locked()

    def _recover_locked(self) -> None:
        if self._marker.exists():
            self._finish_commit(json.loads(self._marker.read_text(encoding="utf-8")))
        elif self._staging.exists():
            shutil.rmtree(self._staging, ignore_errors=True)  # roll back pre-commit staging

    # -- operations -------------------------------------------------------

    def enable(self, token: str) -> None:
        cipher = self._require_cipher()
        with self._lock.acquire():
            self._recover_locked()
            if self._manifest_store.load() is not None:
                raise EncryptionStateError("the store is already encrypted")
            manifest, data_key = cipher.create_envelope(token)
            self._stage(lambda blob: cipher.encrypt(data_key, blob))
            self._commit({"op": "enable", "manifest": _dump_manifest(manifest)})

    def disable(self, token: str) -> None:
        cipher = self._require_cipher()
        with self._lock.acquire():
            self._recover_locked()
            manifest = self._manifest_store.load()
            if manifest is None:
                raise EncryptionStateError("the store is not encrypted")
            data_key = cipher.open_envelope(token, manifest)  # raises on a wrong token
            self._stage(lambda blob: cipher.decrypt(data_key, blob))
            self._commit({"op": "disable"})

    def rotate(self, old_token: str, new_token: str) -> None:
        cipher = self._require_cipher()
        with self._lock.acquire():
            self._recover_locked()
            manifest = self._manifest_store.load()
            if manifest is None:
                raise EncryptionStateError("the store is not encrypted")
            data_key = cipher.open_envelope(old_token, manifest)  # raises on a wrong token
            # re-wrap the same data key: blobs are never re-encrypted, only the
            # small manifest changes (an atomic write).
            self._manifest_store.save(cipher.rewrap(data_key, new_token))

    def invalidate(self) -> None:
        """Crypto-shred / format: drop the wrapped key and wipe the cache content,
        returning to a clean, empty, public store. Needs no token."""
        with self._lock.acquire():
            self._recover_locked()
            self._manifest_store.delete()
            shutil.rmtree(self._blobs, ignore_errors=True)
            shutil.rmtree(self._staging, ignore_errors=True)
            self._marker.unlink(missing_ok=True)
            for name in _WIPE_ON_INVALIDATE:
                (self._root / name).unlink(missing_ok=True)

    # -- internals --------------------------------------------------------

    def _require_cipher(self) -> CipherPort:
        if self._cipher is None:  # pragma: no cover - a wiring error, not a user path
            raise EncryptionStateError("a cipher is required for this operation")
        return self._cipher

    def _stage(self, transform: Callable[[bytes], bytes]) -> None:
        shutil.rmtree(self._staging, ignore_errors=True)
        self._staging.mkdir(parents=True, exist_ok=True)
        for blob in self._blob_files():
            tmp = self._staging / (blob.name + ".tmp")
            tmp.write_bytes(transform(blob.read_bytes()))
            os.replace(tmp, self._staging / blob.name)

    def _commit(self, marker: dict[str, Any]) -> None:
        self._write_marker(marker)
        self._finish_commit(marker)

    def _finish_commit(self, marker: dict[str, Any]) -> None:
        # Move every staged blob into place (atomic per file); idempotent on replay.
        if self._staging.exists():
            self._blobs.mkdir(parents=True, exist_ok=True)
            for staged in self._staging.iterdir():
                if staged.is_file() and not staged.name.endswith(".tmp"):
                    os.replace(staged, self._blobs / staged.name)
            shutil.rmtree(self._staging, ignore_errors=True)
        if marker["op"] == "enable":
            if self._manifest_store.load() is None:
                self._manifest_store.save(_load_manifest(marker["manifest"]))
        else:  # disable
            self._manifest_store.delete()
        self._marker.unlink(missing_ok=True)

    def _write_marker(self, marker: dict[str, Any]) -> None:
        tmp = self._marker.with_name(_MARKER + ".tmp")
        tmp.write_text(json.dumps(marker), encoding="utf-8")
        os.replace(tmp, self._marker)

    def _blob_files(self) -> list[Path]:
        if not self._blobs.exists():
            return []
        # A blob key may legally contain a dot (BlobKey's charset is [A-Za-z0-9._-]), so
        # filter on the actual scratch suffix — skip only the .tmp leftovers, never a
        # dotted key (Y8): the old "no dots" test silently left a dotted-key blob
        # untransformed on enable() and unmovable on disable().
        return [p for p in self._blobs.iterdir() if p.is_file() and not p.name.endswith(".tmp")]


def _dump_manifest(manifest: EncryptionManifest) -> dict[str, str | int]:
    return {
        "version": manifest.version,
        "kdf_salt": base64.b64encode(manifest.kdf_salt).decode("ascii"),
        "wrapped_data_key": base64.b64encode(manifest.wrapped_data_key).decode("ascii"),
    }


def _load_manifest(data: dict[str, Any]) -> EncryptionManifest:
    return EncryptionManifest(
        kdf_salt=base64.b64decode(data["kdf_salt"]),
        wrapped_data_key=base64.b64decode(data["wrapped_data_key"]),
        version=int(data["version"]),
    )
