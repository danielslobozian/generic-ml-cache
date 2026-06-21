# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientRunRequest."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional


@dataclass(frozen=True)
class ClientRunRequest:
    """The DTO the use case constructs and passes to ClientRunnerPort.

    Carries only what the client runner needs to launch the client. The
    command's gmlcache-specific policy fields (cache_mode, persist_output,
    scan_trust) do not appear here — they are the use case's concern, not
    the client runner's.

    allow_paths are the permission-grant folder paths: the client runner
    opens the read-door for these paths without trying to fingerprint them.
    """

    client: str
    model: str
    effort: str
    context: str
    prompt: str
    allow_paths: List[str] = field(default_factory=list)
    client_args: List[str] = field(default_factory=list)
    grants: FrozenSet[str] = field(default_factory=frozenset)
    user_system_prompt: Optional[str] = None
