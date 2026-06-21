# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
#!/usr/bin/env python3
"""A tiny deterministic 'agentic CLI' used only by the test suite.

It stands in for claude/codex/cursor so the cache mechanics (isolation, capture,
replay, modes, checksums) can be tested on every OS without any real binary.

Invoked as::

    python fake_client.py --model M --effort E \
        --context-file CTX --prompt-file PROMPT --system-file SYS

Behavior is driven by directive lines in the prompt (one per line):

    STDOUT <text>            print <text> to stdout
    STDERR <text>            print <text> to stderr
    WRITE <relpath> <b64>    write base64-decoded bytes to <relpath>
    EXIT <n>                 exit with status <n>
    OUTSIDE <abspath>        honor the prime directive: if the system prompt
                             forbids leaving the folder, refuse + exit 9;
                             otherwise (no directive) actually write there

If no directives are given it writes ``output.txt`` and prints ``ok``. It always
ends stdout with a deterministic ``FINGERPRINT`` line derived from its inputs so
tests can prove a replay reproduces the original byte-for-byte.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--effort", required=True)
    ap.add_argument("--context-file", required=True)
    ap.add_argument("--prompt-file")
    ap.add_argument("--prompt-stdin", action="store_true")
    ap.add_argument("--system-file", required=True)
    args = ap.parse_args()

    with open(args.context_file, encoding="utf-8") as fh:
        context = fh.read()
    if args.prompt_stdin:
        # Exercises the launcher's stdin delivery path (the real adapters feed the
        # prompt this way); reading stdin proves a large prompt arrived intact.
        prompt = sys.stdin.read()
    else:
        with open(args.prompt_file, encoding="utf-8") as fh:
            prompt = fh.read()
    with open(args.system_file, encoding="utf-8") as fh:
        system = fh.read()

    exit_code = 0
    directives = [ln for ln in prompt.splitlines() if ln.strip()]
    acted = False

    for line in directives:
        parts = line.split(" ", 2)
        verb = parts[0]
        if verb == "STDOUT" and len(parts) >= 2:
            sys.stdout.write(parts[1] + ("" if len(parts) < 3 else " " + parts[2]) + "\n")
            acted = True
        elif verb == "STDERR" and len(parts) >= 2:
            sys.stderr.write(parts[1] + ("" if len(parts) < 3 else " " + parts[2]) + "\n")
            acted = True
        elif verb == "WRITE" and len(parts) == 3:
            relpath, b64 = parts[1], parts[2]
            data = base64.b64decode(b64.encode("ascii"))
            os.makedirs(os.path.dirname(relpath) or ".", exist_ok=True)
            with open(relpath, "wb") as fh:
                fh.write(data)
            acted = True
        elif verb == "EXIT" and len(parts) >= 2:
            exit_code = int(parts[1])
            acted = True
        elif verb == "SLEEP" and len(parts) >= 2:
            # Sleep far longer than any test timeout so the only way the call ends
            # in time is by being killed -- used to exercise the timeout path.
            time.sleep(float(parts[1]))
            acted = True
        elif verb == "OUTSIDE" and len(parts) >= 2:
            acted = True
            if "PRIME DIRECTIVE" in system:
                sys.stderr.write("refusing to touch path outside the folder\n")
                return 9
            # non-compliant fallback (not exercised by the happy-path tests)
            with open(parts[1], "w", encoding="utf-8") as fh:
                fh.write("escaped")

    if not acted:
        with open("output.txt", "w", encoding="utf-8") as fh:
            fh.write("hello from fake\n")
        sys.stdout.write("ok\n")

    fp = hashlib.sha256(
        (context + "\x00" + prompt + "\x00" + args.model + "\x00" + args.effort).encode("utf-8")
    ).hexdigest()
    sys.stdout.write(f"FINGERPRINT {fp}\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
