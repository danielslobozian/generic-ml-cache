# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""NullDiagnosticsAdapter — silent no-op implementation of DiagnosticsPort."""

from __future__ import annotations

from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort


class NullDiagnosticsAdapter(DiagnosticsPort):
    """Drops every diagnostic event silently. Never raises."""

    def debug(self, msg: str, **context: object) -> None:
        pass

    def info(self, msg: str, **context: object) -> None:
        pass

    def warn(self, msg: str, **context: object) -> None:
        pass

    def error(self, msg: str, exc: BaseException | None = None, **context: object) -> None:
        pass
