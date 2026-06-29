# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemWorkspace — real temp-folder implementation of WorkspacePort.

Each managed run gets two private temp directories: the run folder the client is
launched in, and a config home its settings/credentials are seeded into. The
pre-run snapshot and post-run content diff (SHA-256 per file) are how generated
artifacts are detected without the client having to declare them.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from generic_ml_cache_core.application.domain.model.run.client_config import (
    CredentialFile,
    GrantConfigFile,
)
from generic_ml_cache_core.application.domain.model.run.client_run_result import GeneratedFile
from generic_ml_cache_core.application.domain.model.run.workspace import Snapshot, Workspace
from generic_ml_cache_core.application.port.out.workspace_port import WorkspacePort


def _digests(root: Path) -> Dict[str, str]:
    snap: Dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(root).as_posix()
            snap[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snap


class FilesystemWorkspace(WorkspacePort):
    """Temp-folder workspace: two private dirs per run, snapshot + content diff."""

    def create(self) -> Workspace:
        run_dir = Path(tempfile.mkdtemp(prefix="gmlc-run-"))
        config_home = Path(tempfile.mkdtemp(prefix="gmlc-home-"))
        return Workspace(run_dir=run_dir, config_home=config_home)

    def write_config(self, workspace: Workspace, config_file: Optional[GrantConfigFile]) -> None:
        if config_file is None:
            return
        workspace.config_home.mkdir(parents=True, exist_ok=True)
        (workspace.config_home / config_file.file_name).write_bytes(config_file.content)

    def seed_credentials(self, workspace: Workspace, credentials: List[CredentialFile]) -> None:
        if not credentials:
            return
        workspace.config_home.mkdir(parents=True, exist_ok=True)
        for cred in credentials:
            dest = workspace.config_home / cred.target_name
            try:
                if cred.source.is_dir():
                    shutil.copytree(cred.source, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(cred.source, dest)
            except OSError:
                pass  # best-effort seeding; an env API key still authenticates the run

    def snapshot(self, run_dir: Path) -> Snapshot:
        return Snapshot(digests=_digests(run_dir))

    def capture(self, run_dir: Path, baseline: Snapshot) -> List[GeneratedFile]:
        after = _digests(run_dir)
        captured: List[GeneratedFile] = []
        for rel in sorted(after):
            if baseline.digests.get(rel) != after[rel]:
                captured.append(GeneratedFile(name=rel, content=(run_dir / rel).read_bytes()))
        return captured

    def dispose(self, workspace: Workspace) -> None:
        shutil.rmtree(workspace.run_dir, ignore_errors=True)
        shutil.rmtree(workspace.config_home, ignore_errors=True)
