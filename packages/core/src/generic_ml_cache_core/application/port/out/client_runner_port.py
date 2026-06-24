# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientRunnerPort."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort


class ClientRunnerPort(MlRunnerPort):
    """Outbound port for launching a local ML client in isolation.

    Provides ``execution_kind = LOCAL_MANAGED`` for all managed local adapters.
    Concrete subclasses must still implement ``name`` and ``run``.
    """

    @property
    def execution_kind(self) -> ExecutionKind:
        return ExecutionKind.LOCAL_MANAGED
