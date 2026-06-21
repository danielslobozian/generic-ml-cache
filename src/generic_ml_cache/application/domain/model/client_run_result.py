# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientRunResult and GeneratedFile."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class GeneratedFile:
    """One file the client produced, captured raw — name and bytes only.

    No checksum and no blob key: storage is the use case's job, not the runner's.
    """

    name: str
    content: bytes


@dataclass(frozen=True)
class ClientRunResult:
    """The raw, transient result the ClientRunnerPort returns.

    The contract surface of the runner port — not an adapter-internal type — but
    nothing here is stored yet. The use case turns this into stored Artifacts
    (hash each piece, put it in the blob store) and assembles the MlExecution.
    The runner itself never hashes, never computes a key, never stores.
    """

    exit_code: int
    stdout: str = ""
    stderr: str = ""
    files: List[GeneratedFile] = field(default_factory=list)
