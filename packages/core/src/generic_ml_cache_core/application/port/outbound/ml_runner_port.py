# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MlRunnerPort — the outbound port for single-call (API) ML execution adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest


class MlRunnerPort(ABC):
    """Outbound port for a single-call ML execution: take a request, return a
    result. This is the API path (e.g. a REST provider via :class:`ApiClientPort`).

    Local CLI clients do NOT use this port — they implement :class:`LocalClientPort`,
    which the managed-execution use case drives against an isolated workspace. The
    port carries no client name: by the time ``run`` is called the adapter already
    IS the selected client.
    """

    name: ClassVar[str]
    """The unique adapter name (e.g. ``"anthropic"``, ``"openai"``, ``"gemini"``)."""

    @property
    @abstractmethod
    def execution_kind(self) -> ExecutionKind:
        """The execution kind this adapter belongs to."""

    @abstractmethod
    def run(self, request: MlRequest) -> ClientRunResult:
        """Execute the request and return the raw result. Raises on
        unrecoverable failure."""
