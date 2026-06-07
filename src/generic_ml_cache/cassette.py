# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The cassette: one clean, inspectable JSON file per recorded call.

A cassette captures exactly enough to replay a real call forever:

    launch params : client, model, effort   (explicit fields -- never hashed
                                              with the data, command wording is
                                              never stored)
    input_data    : { context, prompt }     (the cached *input*)
    response      : { stdout, stderr, exit, files: [{path, content, encoding}] }

The **match key** is the exact triple ``(client, model, effort)`` plus the
container-independent checksum of ``input_data``. Two requests match iff their
match keys are equal.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .checksum import checksum_input_data
from .errors import CassetteFormatError

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CapturedFile:
    """A file the client produced, captured relative to its run folder.

    ``path`` is always stored POSIX-style (forward slashes) so a cassette is
    portable across operating systems. ``content`` is the file text for the
    default ``utf-8`` encoding; for bytes that are not valid UTF-8 it is base64
    and ``encoding`` is ``"base64"``.
    """

    path: str
    content: str
    encoding: str = "utf-8"

    def to_bytes(self) -> bytes:
        if self.encoding == "utf-8":
            return self.content.encode("utf-8")
        if self.encoding == "base64":
            return base64.b64decode(self.content.encode("ascii"))
        raise CassetteFormatError(f"unknown file encoding: {self.encoding!r}")

    @classmethod
    def from_bytes(cls, path: str, data: bytes) -> "CapturedFile":
        try:
            return cls(path=path, content=data.decode("utf-8"), encoding="utf-8")
        except UnicodeDecodeError:
            # v0.0.1 targets UTF-8 text; binary is captured losslessly via base64
            # so a stray binary artifact never crashes a recording.
            return cls(
                path=path,
                content=base64.b64encode(data).decode("ascii"),
                encoding="base64",
            )

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "content": self.content, "encoding": self.encoding}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CapturedFile":
        return cls(
            path=d["path"],
            content=d["content"],
            encoding=d.get("encoding", "utf-8"),
        )


@dataclass
class Response:
    stdout: str = ""
    stderr: str = ""
    exit: int = 0
    files: List[CapturedFile] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit": self.exit,
            "files": [f.to_dict() for f in self.files],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Response":
        return cls(
            stdout=d.get("stdout", ""),
            stderr=d.get("stderr", ""),
            exit=int(d.get("exit", 0)),
            files=[CapturedFile.from_dict(x) for x in d.get("files", [])],
        )


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
