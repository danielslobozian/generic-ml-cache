# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""On-disk cassette store: a flat directory of ``<match_key>.json`` files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator, Optional

from generic_ml_cache.adapter.out.metrics.access_registry import EVICT, AccessRegistry
from generic_ml_cache.application.domain.model.cassette import Cassette, match_key
from generic_ml_cache.common.checksum import checksum_input_data
from generic_ml_cache.common.errors import CassetteFormatError

# A cassette is written once, then frozen. These toggle the write bits in a way
# that works on every OS: POSIX clears/sets the user/group/other write bits;
# Windows honors only the owner write bit, which is its read-only attribute. They
# operate on the cache's own files only and touch nothing else on the system.


def _make_readonly(path: Path) -> None:
    os.chmod(path, os.stat(path).st_mode & ~0o222)


def _make_writable(path: Path) -> None:
    os.chmod(path, os.stat(path).st_mode | 0o200)


class CassetteStore:
    """A directory of cassettes, addressed by match key.

    The filename is the match-key digest (O(1) lookup); the file *contents* carry
    the readable client/model/effort/input fields so any cassette is inspectable
    on its own.
    """

    def __init__(self, root: Path, max_bytes: Optional[int] = None) -> None:
        self.root = Path(root)
        # Optional size cap (opt-in). None = keep everything forever (default). When
        # set, a new cassette evicts least-recently-used ones to make room on save.
        self.max_bytes = max_bytes
        self._registry: Optional[AccessRegistry] = None

    @property
    def registry(self) -> AccessRegistry:
        """The access registry for this store (lazy; bound to the store dir)."""
        if self._registry is None:
            self._registry = AccessRegistry(self.root)
        return self._registry

    def _path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def lookup(self, client: str, model: str, effort: str, input_data) -> Optional[Cassette]:
        key = match_key(client, model, effort, checksum_input_data(input_data))
        path = self._path_for(key)
        if not path.exists():
            return None
        cassette = Cassette.from_json(path.read_text(encoding="utf-8"))
        # Defensive: the filename is derived from contents, so they must agree.
        if cassette.match_key != key:
            raise CassetteFormatError(f"cassette {path.name} does not match its filename key")
        return cassette

    def save(self, cassette: Cassette) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path_for(cassette.match_key)
        # Serialize first: if rendering the cassette raises, nothing on disk has
        # been touched yet, so a serialization fault can never half-write a file.
        text = cassette.to_json()
        if self.max_bytes is not None:
            # Opt-in size cap: make room (best-effort) before writing the new
            # cassette. This never blocks or fails the save -- a fresh, paid-for
            # result is always stored, even if that briefly overshoots the cap.
            self._evict_to_fit(len(text.encode("utf-8")), keep_key=cassette.match_key)
        # Write to a per-process unique temp file in the same directory, then
        # atomically replace the target. Same-dir keeps the replace atomic; the
        # unique name stops two concurrent writes to the same key from clobbering
        # one shared temp path. On ANY failure (write or replace, including a
        # signal) the temp file is removed, so a crash mid-write leaves neither a
        # half-written cassette nor a stray temp behind.
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            tmp.write_text(text, encoding="utf-8")
            # If a prior cassette is being replaced (refresh), it is read-only;
            # clear that first so the atomic replace succeeds on every OS. POSIX
            # renames over a read-only target happily; Windows refuses until the
            # read-only attribute is cleared.
            if path.exists():
                _make_writable(path)
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        # A cassette is a finished, write-once artifact, so mark it read-only: a
        # cache hit is a pure read and never writes back here (all mutable
        # bookkeeping lives in the side registry, not the cassette). This is a soft
        # deterrent against a stray edit (the owner can flip it back, root ignores
        # mode bits); we make our best effort and don't pretend to guarantee more.
        _make_readonly(path)
        return path

    def _evict_to_fit(self, incoming_bytes: int, keep_key: str) -> None:
        """Evict least-recently-used cassettes until the incoming one fits under the
        size cap. Best-effort: any failure is swallowed, and it never evicts the key
        about to be written. LRU order is the registry's last-access; a cassette the
        registry has never seen falls back to its file modification time."""
        if self.max_bytes is None:
            return
        try:
            sized = [(p, p.stat().st_size) for p in self.root.glob("*.json") if p.stem != keep_key]
        except OSError:
            return
        total = sum(size for _, size in sized)
        if total + incoming_bytes <= self.max_bytes:
            return
        last_access = self.registry.last_access()

        def idle_rank(item: "tuple[Path, int]") -> float:
            path, _ = item
            try:
                return last_access.get(path.stem, path.stat().st_mtime)
            except OSError:
                return 0.0

        for path, size in sorted(sized, key=idle_rank):
            if total + incoming_bytes <= self.max_bytes:
                break
            if self._evict_one(path):
                total -= size

    def _evict_one(self, path: Path) -> bool:
        """Remove one cassette and log an evict event. Returns True if removed.
        Best-effort: never raises (eviction must not break the save it serves)."""
        try:
            try:
                cassette = Cassette.from_json(path.read_text(encoding="utf-8"))
                self.registry.record(
                    EVICT,
                    match_key=path.stem,
                    client=cassette.client,
                    model=cassette.model,
                    effort=cassette.effort,
                )
            except Exception:
                self.registry.record(EVICT, match_key=path.stem, client="", model="", effort="")
            _make_writable(path)
            path.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def __iter__(self) -> Iterator[Cassette]:
        if not self.root.exists():
            return
        for path in sorted(self.root.glob("*.json")):
            yield Cassette.from_json(path.read_text(encoding="utf-8"))

    def __len__(self) -> int:
        if not self.root.exists():
            return 0
        return sum(1 for _ in self.root.glob("*.json"))
