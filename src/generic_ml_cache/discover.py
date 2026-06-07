# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Client discovery: report which configured clients are present and runnable.

This is **read-only and advisory**. Discovery never chooses a client, never
restricts which model may run, and never gates a call -- it only reports what it
found on this machine. The run is always the validator.

It is the detection half of "detection, not selection": the cache can tell a
caller *what is here*; deciding *what to use* stays with the caller.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .adapters.registry import get_adapter, registered_names
from .errors import ClientNotFound


@dataclass
class ClientStatus:
    """What discovery found for one client. Purely informational."""

    name: str
    present: bool
    executable: Optional[str] = None  # resolved path, when present
    version: Optional[str] = None  # first line of `--version`, best-effort
    detail: Optional[str] = None  # why it's absent, or why version is unknown


def _probe_version(argv: List[str], timeout: float) -> Tuple[Optional[str], Optional[str]]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - any launch failure just means "unknown"
        return None, f"version check failed: {exc}"
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    first = out.splitlines()[0].strip() if out else ""
    return (first or None), (None if first else "no version output")


def probe(name: str, executable: Optional[str] = None, timeout: float = 10.0) -> ClientStatus:
    """Probe one registered client: is its executable present, and what version?

    Never raises for an absent client -- absence is reported in the result.
    """
    adapter = get_adapter(name)
    try:
        exe = adapter.resolve_executable(executable)
    except ClientNotFound as exc:
        return ClientStatus(name=name, present=False, detail=str(exc))
    version, detail = _probe_version(adapter.version_argv(exe), timeout)
    return ClientStatus(name=name, present=True, executable=exe, version=version, detail=detail)


def probe_all(timeout: float = 10.0) -> List[ClientStatus]:
    """Probe every registered client, in name order."""
    return [probe(name, timeout=timeout) for name in registered_names()]
