# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Driver-facing hook for the live-progress stream (W28).

The NDJSON progress writer is an adapter concern — it opens files, so it lives in
the ``adapters`` package (and core's raw-I/O guard keeps it out of the pure core).
A *driver* that also needs to write the same event log (the CLI's async-jobs
runner appends job events in the run-stream format so ``watch`` reads one log) must
not import that adapter directly — that is the exact ``cli -> adapters`` edge W28
removes. Instead it reaches the writer through this composition-root hook: the
driver depends on ``bootstrap``, ``bootstrap`` owns the wiring to ``adapters``.
"""

from __future__ import annotations

from pathlib import Path

from generic_ml_cache_adapters.stream import StreamWriter


def open_progress_stream(path: Path) -> StreamWriter:
    """Open a best-effort NDJSON progress writer at ``path``.

    Safe to call even if ``path`` is unwritable: streaming is then silently
    disabled and the caller's writes are dropped, never raised.
    """
    return StreamWriter(path)
