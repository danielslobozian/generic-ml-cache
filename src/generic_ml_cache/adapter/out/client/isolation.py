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
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

from generic_ml_cache.application.domain.model.client_run_result import (
    ClientRunResult,
    GeneratedFile,
)
from generic_ml_cache.application.domain.model.token_usage import TokenUsage
from generic_ml_cache.application.port.out.base import ClientAdapter
from generic_ml_cache.common.errors import CommandLineTooLong, RunInterrupted
from generic_ml_cache.adapter.out.client.prime_directive import build_system_prompt
from generic_ml_cache.stream import StreamWriter


def _snapshot(root: Path) -> Dict[str, str]:
    """Map each file's POSIX-relative path -> sha256 of its bytes."""
    snap: Dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            rel = path.relative_to(root).as_posix()
            snap[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snap


def _capture_changes(root: Path, baseline: Dict[str, str]) -> List[GeneratedFile]:
    """Return files that were created or modified, sorted by path.

    Deletions are intentionally ignored (the client started in an effectively
    empty folder, so there is nothing meaningful to delete).
    """
    after = _snapshot(root)
    captured: List[GeneratedFile] = []
    for rel in sorted(after):
        if baseline.get(rel) != after[rel]:
            captured.append(GeneratedFile(name=rel, content=(root / rel).read_bytes()))
    return captured


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


def _command_line_limit() -> tuple[str, int, str]:
    """The binding command-line size limit for this OS, as (scope, bytes, label).

    ``scope`` is ``"arg"`` when the limit is on a single argument (Linux's
    ``MAX_ARG_STRLEN``) or ``"total"`` when it is on the whole argument area
    (Windows' ``CreateProcess`` cap; other POSIX ``ARG_MAX``). These are the real
    OS limits, so a call measured at or above one would fail at launch anyway --
    catching it here just makes the failure legible.
    """
    if os.name == "nt":
        return ("total", 32_767, "the Windows command-line limit")
    if sys.platform.startswith("linux"):
        return ("arg", 128 * 1024, "the Linux per-argument limit (MAX_ARG_STRLEN)")
    try:
        arg_max = int(os.sysconf("SC_ARG_MAX"))
    except (ValueError, OSError):
        arg_max = 1024 * 1024
    return ("total", arg_max, "this OS's total argument limit (ARG_MAX)")


def _check_command_line_size(argv: List[str]) -> None:
    """Fail legibly if the assembled command line would exceed the OS limit.

    Only a client that carries the prompt in argv (cursor-agent) can approach this;
    claude and codex put the prompt on stdin, so their command line stays small and
    this never fires for them.
    """
    scope, limit, label = _command_line_limit()
    sizes = [len(arg.encode("utf-8")) for arg in argv]
    measured = max(sizes) if scope == "arg" else sum(sizes) + len(argv)
    # Headroom for the executable path, separators and OS bookkeeping.
    if measured >= limit - 4096:
        raise CommandLineTooLong(
            f"the launched command is ~{measured // 1024} KiB, over {label} "
            f"(~{limit // 1024} KiB). This client takes the prompt as a command-line "
            "argument (it has no stdin path), so a prompt this large cannot be launched "
            "here. Declare large content as input files (--input-file) and reference "
            "them in a short prompt, or use a tier backed by a client that reads the "
            "prompt on stdin (claude/codex)."
        )


def _communicate_streaming(
    proc: subprocess.Popen,
    stdin_text: Optional[str],
    timeout: float | None,
    on_line: Callable[[str], None],
) -> tuple[str, str]:
    """Like ``proc.communicate()``, but hand each stdout line to ``on_line`` as it
    arrives so a live consumer sees progress in real time.

    Stdin is fed and stderr drained on worker threads to avoid the classic pipe
    deadlock, and stdout is read line by line on a third thread. This is the
    portable approach -- it uses threads, not ``select``/``poll`` on file
    descriptors (POSIX-only) -- so it behaves the same on Linux, macOS and Windows.
    Raises ``subprocess.TimeoutExpired`` on timeout, matching ``communicate()`` so
    the caller's teardown path is unchanged.
    """
    out_lines: List[str] = []
    err_chunks: List[str] = []

    def _feed_stdin() -> None:
        if stdin_text is not None and proc.stdin is not None:
            try:
                proc.stdin.write(stdin_text)
            except (OSError, ValueError):
                pass
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except (OSError, ValueError):
                pass

    def _read_stderr() -> None:
        if proc.stderr is None:
            return
        try:
            for chunk in proc.stderr:
                err_chunks.append(chunk)
        except (OSError, ValueError):
            pass

    def _read_stdout() -> None:
        if proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                out_lines.append(line)
                try:
                    on_line(line)
                except Exception:
                    pass  # the live view must never break the run
        except (OSError, ValueError):
            pass

    workers = [
        threading.Thread(target=_feed_stdin, daemon=True),
        threading.Thread(target=_read_stderr, daemon=True),
        threading.Thread(target=_read_stdout, daemon=True),
    ]
    for w in workers:
        w.start()
    proc.wait(timeout=timeout)  # raises TimeoutExpired -> caller tears down
    for w in workers:
        w.join(timeout=5)
    return "".join(out_lines), "".join(err_chunks)


def _run_client(
    argv: List[str],
    cwd: Path,
    stdin_payload: Optional[str],
    timeout: float | None,
    env: Optional[dict] = None,
    on_line: Optional[Callable[[str], None]] = None,
) -> tuple[str, str, int]:
    """Launch the client in its own process group and wait, while honoring a stop
    signal from the caller (the workflow engine, DESIGN cross-app clean stop).

    On SIGTERM/SIGINT the whole group is torn down and ``RunInterrupted`` is raised,
    so the caller records no execution (an interrupted call is not a result). A
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
        env=env,
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
        if on_line is None:
            out, err = proc.communicate(input=stdin_payload if use_stdin else None, timeout=timeout)
        else:
            out, err = _communicate_streaming(
                proc, stdin_payload if use_stdin else None, timeout, on_line
            )
    except subprocess.TimeoutExpired:
        _terminate_group(proc)
        if on_line is None:
            proc.communicate()  # reap the killed child so no zombie lingers
        else:
            # the reader threads hit EOF on the kill; reap without re-reading pipes
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
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
    client_args: Optional[List[str]] = None,
    grants: Optional[List[str]] = None,
    stream_path: Optional[str] = None,
) -> ClientRunResult:
    """Execute the client once in isolation and capture its full result.

    The prime directive is injected here (record time) and is deliberately NOT
    returned as part of the cached input -- it is operational scaffolding. When
    ``allowed_read_paths`` is given (declared input files and/or allow-path
    folders), the directive is widened to let the client read those paths. When
    ``add_dir_paths`` is given, the adapter may *additionally* open a hard
    per-client read door for those folders (e.g. Claude's ``--add-dir``).
    """
    system_prompt = build_system_prompt(user_system_prompt, allowed_read_paths)

    # Opt-in live progress: an NDJSON event file the cache writes as the call runs.
    # Display-only -- it never changes what is recorded (see stream.py).
    writer = StreamWriter(Path(stream_path)) if stream_path else None
    on_line: Optional[Callable[[str], None]] = None
    if writer is not None:
        writer.event(
            "run.start",
            client=adapter.name,
            model=model,
            effort=effort or None,
            grants=",".join(sorted(set(grants or []))) or None,
        )

        def _emit(line: str) -> None:
            event = adapter.stream_event(line)
            if event:
                writer.event(event.pop("kind"), **event)

        on_line = _emit

    try:
        with (
            tempfile.TemporaryDirectory(prefix="gmlc-run-") as tmp,
            tempfile.TemporaryDirectory(prefix="gmlc-home-") as home_tmp,
        ):
            run_dir = Path(tmp)
            # The config home is a SEPARATE folder from run_dir, so the settings
            # file and any seeded credentials are never snapshotted into the
            # stored record and are deleted with the run. Capabilities are enabled by the
            # file written here, not by argv flags (v0.0.16; see docs/reference/grants.md).
            config_home = Path(home_tmp)
            adapter.prepare(run_dir, context, prompt, system_prompt)
            baseline = _snapshot(run_dir)

            argv = adapter.build_argv(
                executable,
                run_dir,
                model,
                effort,
                context,
                prompt,
                system_prompt,
                client_args or [],
                grants or [],
            )
            argv += adapter.read_access_argv(add_dir_paths or [])
            # Forced operational flags a client requires for a grant its file cannot
            # express (Cursor's --force for external network egress).
            argv += adapter.grant_argv(grants or [])
            # Render the client's config file into the redirected home and collect
            # the env (CODEX_HOME/CLAUDE_CONFIG_DIR/CURSOR_CONFIG_DIR) the run needs.
            grant_env = adapter.grant_setup(run_dir, config_home, grants or [])
            run_env = {**os.environ, **grant_env} if grant_env else None
            stdin_payload = adapter.stdin_payload(context, prompt, system_prompt)

            # Fail legibly before the OS rejects an oversize command line (only a
            # client that carries the prompt in argv -- cursor -- can hit this).
            _check_command_line_size(argv)

            # A stop signal here raises RunInterrupted, unwinding before any capture
            # or record write -- an interrupted call leaves no half-written record.
            stdout, stderr, returncode = _run_client(
                argv, run_dir, stdin_payload, timeout, run_env, on_line
            )

            files = _capture_changes(run_dir, baseline)

        # The client ran in its structured (JSON) output mode, so raw stdout carries
        # the answer *and* the usage. The adapter lifts the clean answer back out
        # (what the caller sees on stdout) and reads the normalized usage from the
        # same output. parse_output degrades on its own if the output is unexpected.
        parsed = adapter.parse_output(stdout)

        if writer is not None:
            writer.event(
                "run.end",
                exit=returncode,
                files=len(files),
                input_tokens=parsed.usage.input_tokens if parsed.usage else None,
                output_tokens=parsed.usage.output_tokens if parsed.usage else None,
            )

        # Translate the adapter's parsed usage (its own type) into the core
        # TokenUsage at this boundary; the dict shape is identical.
        token_usage = (
            TokenUsage.from_dict(parsed.usage.to_dict()) if parsed.usage is not None else None
        )
        return ClientRunResult(
            exit_code=returncode,
            stdout=parsed.text,
            stderr=stderr,
            files=files,
            token_usage=token_usage,
        )
    finally:
        if writer is not None:
            writer.close()
