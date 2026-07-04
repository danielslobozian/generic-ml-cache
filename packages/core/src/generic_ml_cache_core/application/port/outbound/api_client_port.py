# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ApiClientPort."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.outbound.ml_runner_port import MlRunnerPort


class ApiClientPort(MlRunnerPort):
    """Outbound port for calling an ML provider API directly.

    Provides ``execution_kind = API`` for all REST adapters. Concrete
    subclasses must still implement ``name`` and ``run``.
    """

    @property
    def execution_kind(self) -> ExecutionKind:
        return ExecutionKind.API
