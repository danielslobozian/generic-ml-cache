# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Workspace + Snapshot — value objects for an isolated managed run.

Core owns the *decision* to run a client in isolation and capture its artifacts.
These are the handles that decision works with; the actual folders and diffing
are performed by a WorkspacePort adapter, so core itself touches no filesystem.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class Workspace:
    """Handle to one isolated run workspace.

    ``run_dir`` is the folder the client is launched in and writes its artifacts
    into (the diff target). ``config_home`` is a private config home the client's
    settings and credentials are seeded into — kept separate from ``run_dir`` so
    nothing written there is ever mistaken for client output.
    """

    run_dir: Path
    config_home: Path


@dataclass(frozen=True)
class Snapshot:
    """An opaque baseline of a directory's contents, taken before a run so the
    post-run diff can tell which files the client created or modified. Core treats
    it as opaque and only hands it back to the WorkspacePort."""

    digests: Mapping[str, str] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(self, "digests", MappingProxyType(dict(self.digests)))
