# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CliProcessRunner — shared subprocess transport for local CLI client adapters.

The subprocess equivalent of an injected HTTP client: a CLI adapter uses it to
make its actual call — launch the client in its own process group, stream stdout
line by line, honour stop signals, and collect the output. It owns NO isolation,
workspace, or file-capture logic; only the launch-and-collect mechanics. The
adapter prepares the argv, calls ``run``, and maps the captured output to a
domain answer.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from generic_ml_cache_core.common.errors import CommandLineTooLong, RunInterrupted


def _terminate_group(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _command_line_limit() -> tuple[str, int, str]:
    if os.name == "nt":
        return ("total", 32_767, "the Windows command-line limit")
    if sys.platform.startswith("linux"):
        return ("arg", 128 * 1024, "the Linux per-argument limit (MAX_ARG_STRLEN)")
    try:
        arg_max = int(os.sysconf("SC_ARG_MAX"))
    except (ValueError, OSError):
        arg_max = 1024 * 1024
    return ("total", arg_max, "this OS's total argument limit (ARG_MAX)")


def _check_command_line_size(argv: list[str]) -> None:
    scope, limit, label = _command_line_limit()
    sizes = [len(arg.encode("utf-8")) for arg in argv]
    measured = max(sizes) if scope == "arg" else sum(sizes) + len(argv)
    if measured >= limit - 4096:
        raise CommandLineTooLong(
            f"the launched command is ~{measured // 1024} KiB, over {label} "
            f"(~{limit // 1024} KiB). This client takes the prompt as a command-line "
            "argument (it has no stdin path), so a prompt this large cannot be launched "
            "here. Declare large content as input files (--input-file) and reference "
            "them in a short prompt, or use a tier backed by a client that reads the "
            "prompt on stdin (claude/codex)."
        )


def _communicate_streaming(  # noqa: C901
    proc: subprocess.Popen,
    stdin_text: str | None,
    timeout: float | None,
    on_line: Callable[[str], None],
) -> tuple[str, str]:
    out_lines: list[str] = []
    err_chunks: list[str] = []

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
                    pass
        except (OSError, ValueError):
            pass

    workers = [
        threading.Thread(target=_feed_stdin, daemon=True),
        threading.Thread(target=_read_stderr, daemon=True),
        threading.Thread(target=_read_stdout, daemon=True),
    ]
    for w in workers:
        w.start()
    proc.wait(timeout=timeout)
    for w in workers:
        w.join(timeout=5)
    return "".join(out_lines), "".join(err_chunks)


class CliProcessRunner:
    """Launch a CLI client in its own process group and collect its output.

    Stateless and reusable; one instance can serve many calls. ``run`` guards the
    command-line size first (so an over-large argv fails with a legible error
    rather than an OS-level launch failure), then launches and collects.
    """

    def run(  # noqa: C901
        self,
        argv: list[str],
        cwd: Path,
        stdin_payload: str | None = None,
        timeout: float | None = None,
        env: dict | None = None,
        on_line: Callable[[str], None] | None = None,
    ) -> tuple[str, str, int]:
        """Launch ``argv`` in ``cwd``, honour stop signals, return (stdout, stderr, exit)."""
        _check_command_line_size(argv)
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
        previous: dict[int, Any] = {}
        installed: list[int] = []

        def _on_stop(signum, _frame):
            stopped["signum"] = signum
            _terminate_group(proc)

        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    previous[sig] = signal.signal(sig, _on_stop)
                    installed.append(sig)
                except (ValueError, OSError, RuntimeError):
                    pass

        try:
            if on_line is None:
                out, err = proc.communicate(
                    input=stdin_payload if use_stdin else None, timeout=timeout
                )
            else:
                out, err = _communicate_streaming(
                    proc, stdin_payload if use_stdin else None, timeout, on_line
                )
        except subprocess.TimeoutExpired:
            _terminate_group(proc)
            if on_line is None:
                proc.communicate()
            else:
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
