# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Live progress stream: an opt-in NDJSON event file written as a call runs.

The cache is the one running the client, so it is the right place to surface what
the client is doing *right now* -- for a human watching a long call, and (later)
for the workflow engine relaying progress to its own user.

This is infrastructure (it opens files), so it lives in the adapters package, not
the pure core. It sits at the package top level — like ``discovery`` — because it
is shared by an out adapter (the CLI runtime) and a driver (the CLI's async-jobs
runner); it is not itself a driven ``adapter/outbound`` implementation behind a port.

Design:

* **Display-only.** The stream never changes what the cache records or the cache
  key. It is a *view* of the run, not a second source of truth.
* **A regular file** is the transport. It is the one streaming channel that
  behaves identically on Linux, macOS and Windows -- no sockets, no named pipes
  (POSIX-only), no ``select``. A consumer (a human ``tail -f``, or a parent
  process reading line by line) just opens it read-only and reads new lines.
* **NDJSON / JSON Lines.** One self-contained JSON object per line, ``\\n``
  separated, flushed as written, so each event is readable the moment it lands
  and the file is appendable without parsing what came before.
* **Best-effort.** A write that fails (full disk, bad path) is dropped, never
  raised -- a progress view must not be able to break the real call.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class StreamWriter:
    """Append NDJSON progress events to ``path``. Safe to construct even if the
    path is unwritable: streaming is then silently disabled and the call runs
    unaffected."""

    def __init__(self, path: Path) -> None:
        self._fh: Any | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Text append; newline="\n" writes bare line feeds on every OS (no
            # CRLF translation), which is what NDJSON consumers expect.
            self._fh = open(path, "a", encoding="utf-8", newline="\n")
        except OSError:
            self._fh = None  # streaming disabled; the run still proceeds

    def event(self, kind: str, **fields: Any) -> None:
        """Write one event line: ``{"ts": <epoch>, "kind": <kind>, ...}``.
        Fields that are ``None`` are omitted so the line stays compact."""
        if self._fh is None:
            return
        record = {"ts": round(time.time(), 3), "kind": kind}
        record.update({k: v for k, v in fields.items() if v is not None})
        try:
            self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            self._fh.flush()
        except (OSError, ValueError, TypeError):
            pass  # drop the event rather than fail the run

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            finally:
                self._fh = None
