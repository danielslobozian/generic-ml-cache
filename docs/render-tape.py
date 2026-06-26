#!/usr/bin/env python3
"""render-tape.py <cassette.tape>

Install gmlcache from source in a fresh isolated venv, point GMLCACHE_CONFIG
at a temporary store, then render the VHS cassette.  The temp environment is
cleaned up on exit.

Usage:
    python3 docs/render-tape.py docs/tapes/purge.tape
    python3 docs/render-tape.py docs/tapes/sessions.tape
    python3 docs/render-tape.py docs/tapes/evict-lru.tape
    python3 docs/render-tape.py docs/tapes/evict-stale.tape

Requires: python3 (3.11+), vhs (https://github.com/charmbracelet/vhs)

Tapes that call a real client (demo.tape, api.tape, …) still need that client
installed and authenticated; this script only wires the cache itself.
Tapes that use --executable $GMLCACHE_FAKE_CLAUDE (purge.tape, sessions.tape,
evict-lru.tape, evict-stale.tape) need no real API key — the fake script reads
the prompt from stdin and echoes it back, so list/inspect output is readable.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _venv_bin(venv: Path) -> Path:
    """Return the Scripts/ or bin/ directory for this platform."""
    return venv / ("Scripts" if sys.platform == "win32" else "bin")


def _exe(venv: Path, name: str) -> Path:
    """Return the path to an executable inside the venv."""
    suffix = ".exe" if sys.platform == "win32" else ""
    return _venv_bin(venv) / (name + suffix)


def _fake_client(tmp: Path) -> Path:
    """Write a minimal fake client script and return its path.

    Reads the first non-empty line from stdin (the prompt delivered by the
    claude adapter) and echoes it back as a one-line cached response.  This
    makes eviction demos meaningful: the list command shows which prompt each
    surviving entry belongs to.  parse_output degrades gracefully when stdout
    is plain text rather than JSON.
    """
    if sys.platform == "win32":
        script = tmp / "fake_claude.bat"
        script.write_text(
            "@echo off\n"
            "set /p PROMPT=\n"
            'echo Cached: %PROMPT%\n',
            encoding="utf-8",
        )
    else:
        script = tmp / "fake_claude.sh"
        script.write_text(
            "#!/bin/sh\n"
            # Read lines until we find a non-empty one (skip blank context lines).
            "while IFS= read -r line; do\n"
            '  [ -n "$line" ] && echo "Cached: $line" && exit 0\n'
            "done\n"
            "echo 'Cached: (empty prompt)'\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    return script


def _output_path(tape: Path) -> str | None:
    """Extract the Output directive from the tape file."""
    for line in tape.read_text(encoding="utf-8").splitlines():
        if line.startswith("Output "):
            return line.split(None, 1)[1].strip()
    return None


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <path/to/cassette.tape>", file=sys.stderr)
        sys.exit(1)

    tape = Path(sys.argv[1]).resolve()
    repo_root = Path(__file__).resolve().parent.parent

    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        venv = tmp / "venv"

        print(f"→ Installing gmlcache from source in {tmp} …")
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        subprocess.run(
            [
                str(_exe(venv, "pip")), "install", "-q",
                "-e", str(repo_root / "packages" / "core"),
                "-e", str(repo_root / "packages" / "cli"),
                "-e", str(repo_root / "packages" / "daemon"),
            ],
            check=True,
        )

        # Isolated store and config
        store = tmp / "store"
        store.mkdir()
        config = tmp / "config.ini"
        config.write_text(
            f"[generic-ml-cache]\nstore = {store}\n", encoding="utf-8"
        )

        fake = _fake_client(tmp)

        print(f"→ Store  : {store}")
        print(f"→ Config : {config}")
        print(f"→ Rendering {tape} …")

        # Build the child environment: isolated config, venv on PATH, fake client.
        path_sep = ";" if sys.platform == "win32" else ":"
        env = os.environ.copy()
        env["GMLCACHE_CONFIG"] = str(config)
        env["GMLCACHE_FAKE_CLAUDE"] = str(fake)
        env["PATH"] = str(_venv_bin(venv)) + path_sep + env.get("PATH", "")

        subprocess.run(["vhs", str(tape)], check=True, cwd=str(repo_root), env=env)

    output = _output_path(tape)
    if output:
        print(f"→ Written : {output}")


if __name__ == "__main__":
    main()
