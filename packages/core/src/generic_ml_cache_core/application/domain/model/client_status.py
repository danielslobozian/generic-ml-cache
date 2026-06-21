"""ClientStatus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ClientStatus:
    """What discovery found for one client. Purely informational."""

    name: str
    present: bool
    executable: Optional[str] = None  # resolved path, when present
    version: Optional[str] = None  # first line of `--version`, best-effort
    detail: Optional[str] = None  # why it's absent, or why version is unknown
