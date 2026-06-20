"""CapturedFile."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Dict

from generic_ml_cache.common.errors import CassetteFormatError


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
