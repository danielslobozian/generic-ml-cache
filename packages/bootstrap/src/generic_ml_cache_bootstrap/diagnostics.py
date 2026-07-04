# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Driver-facing hook for the diagnostics (logging) port (W28).

Choosing whether to log, at what level, and to which file is *driver policy* — the
CLI resolves it from flags + env + config, the daemon from env. But constructing
the concrete diagnostics adapter (null vs structlog) is infrastructure, and a
driver must not import a concrete ``adapters.…diagnostics`` class to do it — that
is the ``cli``/``daemon`` -> ``adapters`` edge W28 removes. The driver resolves the
settings and hands them here; the composition root builds the port.
"""

from __future__ import annotations

from pathlib import Path

from generic_ml_cache_adapters.adapter.outbound.diagnostics.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_adapters.adapter.outbound.diagnostics.structlog_diagnostics_adapter import (
    StructlogDiagnosticsAdapter,
)
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort


def build_diagnostics(log_level: str | None, log_file: Path | None = None) -> DiagnosticsPort:
    """Build the diagnostics port from a driver's resolved logging settings.

    An empty/absent ``log_level`` selects the quiet no-op adapter (the store still
    works; nothing is logged). Otherwise structured logging is written to
    ``log_file`` (its parent directory is created), which must be provided.
    """
    if not log_level:
        return NullDiagnosticsAdapter()
    if log_file is None:
        raise ValueError("a log file is required when a log level is set")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    return StructlogDiagnosticsAdapter(log_file, level=log_level)
