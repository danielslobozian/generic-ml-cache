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

    input_file_paths are the declared files the client is granted read access to
    (their content is already fingerprinted into the key); allow_paths are the
    permission-grant folder paths the client may scan. The runner opens the
    read-door for both; it fingerprints neither (that already happened).
    """

    client: str
    model: str
    effort: str
    context: str
    prompt: str
    input_file_paths: List[str] = field(default_factory=list)
    allow_paths: List[str] = field(default_factory=list)
    client_args: List[str] = field(default_factory=list)
    grants: FrozenSet[str] = field(default_factory=frozenset)
    user_system_prompt: Optional[str] = None
