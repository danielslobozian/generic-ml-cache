# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""WorkspacePort — outbound port for the managed-run workspace lifecycle.

The managed-execution use case owns the *decision* to isolate a run and capture
its artifacts. This port is the *mechanism* it drives: create the temp folders,
snapshot the run folder before launch, diff it afterwards to capture generated
files, and dispose of everything. It lives behind a port so core performs no
filesystem I/O itself — the implementation is a driven adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from generic_ml_cache_core.application.domain.model.run.client_config import (
    CredentialFile,
    GrantConfigFile,
)
from generic_ml_cache_core.application.domain.model.run.client_run_result import GeneratedFile
from generic_ml_cache_core.application.domain.model.run.workspace import Snapshot, Workspace


class WorkspacePort(ABC):
    """Create, configure, snapshot, diff, and dispose an isolated managed-run
    workspace. The *what* to write (config file, credentials) comes from the
    client adapter as descriptors; this port performs the writing."""

    @abstractmethod
    def create(self) -> Workspace:
        """Make a fresh workspace (run folder + private config home)."""

    @abstractmethod
    def write_config(self, workspace: Workspace, config_file: Optional[GrantConfigFile]) -> None:
        """Write the client's grant config file into the config home (no-op if None)."""

    @abstractmethod
    def seed_credentials(self, workspace: Workspace, credentials: List[CredentialFile]) -> None:
        """Copy the client's credential/token files into the config home."""

    @abstractmethod
    def snapshot(self, run_dir: Path) -> Snapshot:
        """Capture the run folder's pre-launch baseline."""

    @abstractmethod
    def capture(self, run_dir: Path, baseline: Snapshot) -> List[GeneratedFile]:
        """Return the files created or modified since ``baseline``."""

    @abstractmethod
    def dispose(self, workspace: Workspace) -> None:
        """Remove the workspace and all its contents."""
