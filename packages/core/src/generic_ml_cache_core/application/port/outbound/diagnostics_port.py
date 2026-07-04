# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""DiagnosticsPort — outbound port for technical diagnostic logging.

Core emits through this port; it never imports a logging library directly.
The edge (CLI, daemon) supplies the concrete adapter with its level threshold,
format, and destination. Quiet mode wires a NullDiagnosticsAdapter so that
diagnostics can never reach the replay channel by construction (R4).

Contract (R5): implementations must never raise. A diagnostics failure must
not break or alter an execution.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class DiagnosticsPort(ABC):
    """Severity-leveled technical diagnostics port.

    Call sites pass free-form keyword context that the adapter formats
    alongside the message:

        diag.info("cache hit", key=execution_key, session=session_id)
        diag.error("registry write failed", exc=e, key=execution_key)
    """

    @abstractmethod
    def debug(self, msg: str, **context: object) -> None:
        """Emit a DEBUG-level diagnostic. Must never raise."""

    @abstractmethod
    def info(self, msg: str, **context: object) -> None:
        """Emit an INFO-level diagnostic. Must never raise."""

    @abstractmethod
    def warn(self, msg: str, **context: object) -> None:
        """Emit a WARN-level diagnostic. Must never raise."""

    @abstractmethod
    def error(self, msg: str, exc: BaseException | None = None, **context: object) -> None:
        """Emit an ERROR-level diagnostic, optionally with a caught exception
        whose traceback the adapter renders. Must never raise."""
