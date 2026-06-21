# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunApiExecutionService."""

from __future__ import annotations

from typing import Tuple

from generic_ml_cache.application.domain.model.api_call_identity import ApiCallIdentity
from generic_ml_cache.application.domain.model.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.client_run_result import ClientRunResult
from generic_ml_cache.application.domain.model.execution_kind import ExecutionKind
from generic_ml_cache.application.domain.service.message_fingerprinting import fingerprint_messages
from generic_ml_cache.application.port.inbound.run_api_execution_command import (
    RunApiExecutionCommand,
)
from generic_ml_cache.application.port.inbound.run_api_execution_use_case import (
    RunApiExecutionUseCase,
)
from generic_ml_cache.application.port.out.api_client_port import ApiClientPort
from generic_ml_cache.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache.application.port.out.metrics_port import MetricsPort
from generic_ml_cache.application.usecase.cached_ml_execution_service import (
    CachedMlExecutionService,
)


class RunApiExecutionService(CachedMlExecutionService, RunApiExecutionUseCase):
    """Record-or-replay a direct ML provider API call.

    Implements the inbound port over the shared cached-execution flow, supplying
    the API specifics: the identity is the provider, model, and a fingerprint of
    the message list; the call goes through the API client port (no subprocess,
    no files); and executions are tagged API. An API call is always cacheable.
    """

    def __init__(
        self,
        api_client: ApiClientPort,
        blob_store: BlobStorePort,
        repository: ExecutionRepositoryPort,
        metrics: MetricsPort,
    ) -> None:
        super().__init__(blob_store, repository, metrics)
        self._api_client = api_client

    def _build_identity(self, command: RunApiExecutionCommand) -> CallIdentity:
        return ApiCallIdentity(
            provider=command.provider,
            model=command.model,
            messages_fingerprint=fingerprint_messages(command.messages),
        )

    def _run_client(self, command: RunApiExecutionCommand) -> ClientRunResult:
        return self._api_client.run(command.provider, command.model, command.messages)

    def _execution_kind(self) -> ExecutionKind:
        return ExecutionKind.API

    def _journal_fields(self, command: RunApiExecutionCommand) -> Tuple[str, str, str]:
        # The provider plays the role of "client" in the journal; no effort concept.
        return command.provider, command.model, ""
