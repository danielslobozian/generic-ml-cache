# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Run a client in an isolated folder and capture exactly what it produced.

Isolation is correctness, not just hygiene: only by running the client in a
folder of our own can we attribute created/modified files to *the run* rather
than to whatever the user already had lying around. Before/after diffing in a
shared folder would be unsound.

Flow:
    1. make a fresh temp folder
    2. adapter.prepare(...) writes the client's input files there
    3. snapshot the folder  <-- baseline includes step-2 files, so they are
                                NOT mistaken for client output
    4. launch the client (cwd = the folder)
    5. snapshot again; diff against the baseline -> captured files
    6. delete the folder
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .adapters.base import ClientAdapter
from .cassette import CapturedFile, Response
from .prime_directive import build_system_prompt


def _snapshot(root: Path) -> Dict[str, str]:
    """Map each file's POSIX-relative path -> sha256 of its bytes."""
    snap: Dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(root).as_posix()
            snap[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snap


def _capture_changes(root: Path, baseline: Dict[str, str]) -> List[CapturedFile]:
    """Return files that were created or modified, sorted by path.

    Deletions are intentionally ignored in v0.0.1 (the client started in an
    effectively empty folder, so there is nothing meaningful to delete).
    """
    after = _snapshot(root)
    captured: List[CapturedFile] = []
    for rel in sorted(after):
        if baseline.get(rel) != after[rel]:
            data = (root / rel).read_bytes()
            captured.append(CapturedFile.from_bytes(rel, data))
    return captured


@dataclass
class RunResult:
    response: Response
    run_dir: str  # the (already-deleted) isolated path, for diagnostics


def record_real_call(
    adapter: ClientAdapter,
    executable: str,
    model: str,
    effort: str,
    context: str,
    prompt: str,
    user_system_prompt: str | None = None,
    timeout: float | None = None,
) -> RunResult:
    """Execute the client once in isolation and capture its full response.

    The prime directive is injected here (record time) and is deliberately NOT
    returned as part of the cached input -- it is operational scaffolding.
    """
    system_prompt = build_system_prompt(user_system_prompt)

    with tempfile.TemporaryDirectory(prefix="gmlc-run-") as tmp:
        run_dir = Path(tmp)
        adapter.prepare(run_dir, context, prompt, system_prompt)
        baseline = _snapshot(run_dir)

        argv = adapter.build_argv(
            executable, run_dir, model, effort, context, prompt, system_prompt
        )
        stdin_payload = adapter.stdin_payload(context, prompt, system_prompt)

        completed = subprocess.run(
            argv,
            cwd=str(run_dir),
            input=stdin_payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        files = _capture_changes(run_dir, baseline)

    response = Response(
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        exit=completed.returncode,
        files=files,
    )
    return RunResult(response=response, run_dir=str(run_dir))
