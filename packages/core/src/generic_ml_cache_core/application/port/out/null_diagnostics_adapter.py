# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""NullDiagnosticsAdapter — silent no-op implementation of DiagnosticsPort.

Used as the default when no logging destination is configured (quiet mode).
Wiring this adapter guarantees that diagnostics can never reach the replay
channel by construction rather than by convention (ROADMAP R4).
"""

from __future__ import annotations

from typing import Optional

from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort


class NullDiagnosticsAdapter(DiagnosticsPort):
    """Drops every diagnostic event silently. Never raises."""

    def debug(self, msg: str, **context: object) -> None:
        pass  # intentional no-op: null object silently discards all diagnostics

    def info(self, msg: str, **context: object) -> None:
        pass  # intentional no-op: null object silently discards all diagnostics

    def warn(self, msg: str, **context: object) -> None:
        pass  # intentional no-op: null object silently discards all diagnostics

    def error(self, msg: str, exc: Optional[BaseException] = None, **context: object) -> None:
        pass  # intentional no-op: null object silently discards all diagnostics
