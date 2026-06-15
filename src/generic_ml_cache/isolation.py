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
import os
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .adapters.base import ClientAdapter
from .cassette import CapturedFile, Response
from .errors import RunInterrupted
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


def _terminate_group(proc: subprocess.Popen) -> None:
    """Tear down the client and everything it spawned. The client runs in its own
    process group / session, so one signal to the group reaches grandchildren too --
    no orphans left behind. Best-effort: a race where the child already exited is
    fine (that is exactly what we wanted)."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:  # Windows has no killpg; terminate the child process directly
            proc.terminate()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _run_client(
    argv: List[str], cwd: Path, stdin_payload: Optional[str], timeout: float | None
) -> tuple[str, str, int]:
    """Launch the client in its own process group and wait, while honoring a stop
    signal from the caller (the workflow engine, DESIGN cross-app clean stop).

    On SIGTERM/SIGINT the whole group is torn down and ``RunInterrupted`` is raised,
    so the caller records no cassette (an interrupted call is not a result). A
    timeout keeps the prior contract: kill the group and re-raise ``TimeoutExpired``.

    Signal handlers can only be installed on the main thread; off it (a host that
    embeds the cache on a worker thread) we still run and still tear down on timeout
    -- we simply cannot catch a process signal there, which is the host's to manage.
    """
    group_kwargs: dict = (
        {"start_new_session": True}
        if os.name == "posix"
        else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    )
    use_stdin = stdin_payload is not None
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        stdin=subprocess.PIPE if use_stdin else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **group_kwargs,
    )

    stopped: dict[str, int | None] = {"signum": None}
    previous: dict[int, object] = {}
    installed: List[int] = []

    def _on_stop(signum, _frame):
        # Killing the child makes communicate() return on its own; we record the
        # signal and raise *after* it returns, never from inside the handler.
        stopped["signum"] = signum
        _terminate_group(proc)

    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                previous[sig] = signal.signal(sig, _on_stop)
                installed.append(sig)
            except (ValueError, OSError, RuntimeError):
                pass  # not settable on this platform/context; carry on without it

    try:
        out, err = proc.communicate(input=stdin_payload if use_stdin else None, timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_group(proc)
        proc.communicate()  # reap the killed child so no zombie lingers
        raise
    finally:
        for sig in installed:
            signal.signal(sig, previous[sig])

    if stopped["signum"] is not None:
        raise RunInterrupted(
            f"client run was stopped (signal {stopped['signum']}) before it completed"
        )
    return out or "", err or "", proc.returncode


def record_real_call(
    adapter: ClientAdapter,
    executable: str,
    model: str,
    effort: str,
    context: str,
    prompt: str,
    user_system_prompt: str | None = None,
    timeout: float | None = None,
    allowed_read_paths: Optional[List[str]] = None,
    add_dir_paths: Optional[List[str]] = None,
) -> RunResult:
    """Execute the client once in isolation and capture its full response.

    The prime directive is injected here (record time) and is deliberately NOT
    returned as part of the cached input -- it is operational scaffolding. When
    ``allowed_read_paths`` is given (declared input files and/or allow-path
    folders), the directive is widened to let the client read those paths. When
    ``add_dir_paths`` is given, the adapter may *additionally* open a hard
    per-client read door for those folders (e.g. Claude's ``--add-dir``).
    """
    system_prompt = build_system_prompt(user_system_prompt, allowed_read_paths)

    with tempfile.TemporaryDirectory(prefix="gmlc-run-") as tmp:
        run_dir = Path(tmp)
        adapter.prepare(run_dir, context, prompt, system_prompt)
        baseline = _snapshot(run_dir)

        argv = adapter.build_argv(
            executable, run_dir, model, effort, context, prompt, system_prompt
        )
        argv += adapter.read_access_argv(add_dir_paths or [])
        stdin_payload = adapter.stdin_payload(context, prompt, system_prompt)

        # A stop signal here raises RunInterrupted, unwinding before any capture or
        # cassette write -- an interrupted call leaves no half-written record.
        stdout, stderr, returncode = _run_client(argv, run_dir, stdin_payload, timeout)

        files = _capture_changes(run_dir, baseline)

    response = Response(
        stdout=stdout,
        stderr=stderr,
        exit=returncode,
        files=files,
    )
    return RunResult(response=response, run_dir=str(run_dir))
