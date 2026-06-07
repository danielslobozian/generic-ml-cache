# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""On-disk cassette store: a flat directory of ``<match_key>.json`` files."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional

from .cassette import Cassette, match_key
from .checksum import checksum_input_data
from .errors import CassetteFormatError


class CassetteStore:
    """A directory of cassettes, addressed by match key.

    The filename is the match-key digest (O(1) lookup); the file *contents* carry
    the readable client/model/effort/input fields so any cassette is inspectable
    on its own.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

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
        # Atomic-ish write: temp file then replace, so a crash never leaves a
        # half-written cassette that would later fail to parse.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(cassette.to_json(), encoding="utf-8")
        tmp.replace(path)
        return path

    def __iter__(self) -> Iterator[Cassette]:
        if not self.root.exists():
            return
        for path in sorted(self.root.glob("*.json")):
            yield Cassette.from_json(path.read_text(encoding="utf-8"))

    def __len__(self) -> int:
        if not self.root.exists():
            return 0
        return sum(1 for _ in self.root.glob("*.json"))
