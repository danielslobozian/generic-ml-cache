# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""MlRunnerPort — the common outbound port for all ML execution adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest


class MlRunnerPort(ABC):
    """Common root for every ML execution adapter — local or API.

    The use case depends only on this interface. The concrete adapter behind it
    (a managed local runner, a passthrough runner, a REST API client) is wired
    at the composition root. The port carries no client name: the adapter
    already IS the selected client.
    """

    name: ClassVar[str]
    """The unique adapter name (e.g. ``"claude"``, ``"anthropic"``, ``"pass-claude"``)."""

    @property
    @abstractmethod
    def execution_kind(self) -> ExecutionKind:
        """The execution kind this adapter belongs to."""

    @abstractmethod
    def run(self, request: MlRequest) -> ClientRunResult:
        """Execute the request and return the raw result. Raises on
        unrecoverable failure."""
