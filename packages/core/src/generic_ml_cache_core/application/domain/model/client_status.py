"""ClientStatus."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClientStatus:
    """What discovery found for one client. Purely informational."""

    name: str
    present: bool
    executable: str | None = None  # resolved path, when present
    version: str | None = None  # first line of `--version`, best-effort
    detail: str | None = None  # why it's absent, or why version is unknown
