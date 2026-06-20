"""Response."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .captured_file import CapturedFile
from .usage import Usage


@dataclass
class Response:
    stdout: str = ""
    stderr: str = ""
    exit: int = 0
    files: List[CapturedFile] = field(default_factory=list)
    #: Normalized token/cost envelope for the recorded call, or ``None`` when no
    #: usage was captured -- a client that reported none, an output that could not
    #: be parsed, or a pre-usage (schema 1) cassette. ``None`` means "unknown",
    #: never "zero".
    usage: Optional[Usage] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit": self.exit,
            "files": [f.to_dict() for f in self.files],
            "usage": self.usage.to_dict() if self.usage is not None else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Response":
        usage_dict = d.get("usage")
        return cls(
            stdout=d.get("stdout", ""),
            stderr=d.get("stderr", ""),
            exit=int(d.get("exit", 0)),
            files=[CapturedFile.from_dict(x) for x in d.get("files", [])],
            usage=Usage.from_dict(usage_dict) if usage_dict is not None else None,
        )
