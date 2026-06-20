# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The cassette: one clean, inspectable JSON file per recorded call.

A cassette captures exactly enough to replay a real call forever:

    launch params : client, model, effort   (explicit fields -- never hashed
                                              with the data, command wording is
                                              never stored)
    input_data    : { context, prompt }     (the cached *input*)
    response      : { stdout, stderr, exit, files: [...], usage }
                                             (usage: normalized token/cost
                                              envelope + the client's raw block,
                                              or null when none was captured)

The **match key** is the exact triple ``(client, model, effort)`` plus the
container-independent checksum of ``input_data``. Two requests match iff their
match keys are equal.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict

from .captured_file import CapturedFile as CapturedFile
from .checksum import checksum_input_data
from .errors import CassetteFormatError
from .response import Response as Response

SCHEMA_VERSION = 2


@dataclass
class Cassette:
    client: str
    model: str
    effort: str
    input_data: Dict[str, str]
    response: Response = field(default_factory=Response)
    schema_version: int = SCHEMA_VERSION

    # -- keys -------------------------------------------------------------
    @property
    def input_checksum(self) -> str:
        return checksum_input_data(self.input_data)

    @property
    def match_key(self) -> str:
        """Stable digest of (client, model, effort) + checksum(input_data).

        Used as the on-disk filename. The launch params are explicit, separate
        fields -- they are part of the *key* but are never folded into the
        *data* checksum.
        """
        return match_key(self.client, self.model, self.effort, self.input_checksum)

    # -- serialization ----------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "client": self.client,
            "model": self.model,
            "effort": self.effort,
            # checksum is denormalized into the file purely for human inspection;
            # matching always recomputes it from input_data.
            "input_checksum": self.input_checksum,
            "input_data": dict(self.input_data),
            "response": self.response.to_dict(),
        }

    def to_json(self) -> str:
        # sort_keys + indent => stable, diff-friendly, inspectable files.
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Cassette":
        try:
            return cls(
                client=d["client"],
                model=d["model"],
                effort=d["effort"],
                input_data=dict(d["input_data"]),
                response=Response.from_dict(d.get("response", {})),
                schema_version=int(d.get("schema_version", SCHEMA_VERSION)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CassetteFormatError(f"malformed cassette: {exc}") from exc

    @classmethod
    def from_json(cls, text: str) -> "Cassette":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CassetteFormatError(f"invalid JSON: {exc}") from exc
        return cls.from_dict(data)


def match_key(client: str, model: str, effort: str, input_checksum: str) -> str:
    """Digest the full match tuple into a filesystem-safe identifier."""
    h = hashlib.sha256()
    for part in (client, model, effort, input_checksum):
        h.update(part.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()
