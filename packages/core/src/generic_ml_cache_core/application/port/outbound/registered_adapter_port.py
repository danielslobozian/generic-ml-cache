# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RegisteredAdapterPort — the minimal contract every registered adapter satisfies.

The registry holds heterogeneous adapters: API adapters (which run via
:class:`MlRunnerPort`) and local client adapters (which run via
:class:`LocalClientPort`). What they share — and all the registry itself needs —
is an identity: a ``name`` and the ``execution_kind`` they belong to. Consumers
narrow to the richer port (MlRunnerPort / LocalClientPort) for the actual call.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind


@runtime_checkable
class RegisteredAdapterPort(Protocol):
    """Identity shared by every registered adapter, API or local."""

    name: str

    @property
    def execution_kind(self) -> ExecutionKind: ...
