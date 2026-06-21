# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunPassthroughExecutionService."""

from __future__ import annotations

from typing import Tuple

from generic_ml_cache.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)
from generic_ml_cache.application.port.inbound.run_passthrough_execution_command import (
    RunPassthroughExecutionCommand,
)
from generic_ml_cache.application.port.inbound.run_passthrough_execution_use_case import (
    RunPassthroughExecutionUseCase,
)
from generic_ml_cache.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache.application.port.out.metrics_port import MetricsPort
from generic_ml_cache.application.port.out.passthrough_runner_port import PassthroughRunnerPort
from generic_ml_cache.application.usecase.cached_ml_execution_service import (
    CachedMlExecutionService,
)
from generic_ml_cache.common.checksum import fingerprint_arguments


class RunPassthroughExecutionService(CachedMlExecutionService, RunPassthroughExecutionUseCase):
    """Record-or-replay a passthrough (alias) client call.

    Implements the inbound port over the shared cached-execution flow, supplying
    the passthrough specifics: the identity is the client plus a fingerprint of
    the opaque native args, the client runs via the passthrough runner (no
    isolation, no file capture), and executions are tagged LOCAL_PASSTHROUGH. A
    passthrough is always cacheable, so it keeps the base's default.
    """

    def __init__(
        self,
        passthrough_runner: PassthroughRunnerPort,
        blob_store: BlobStorePort,
        repository: ExecutionRepositoryPort,
        metrics: MetricsPort,
    ) -> None:
        super().__init__(blob_store, repository, metrics)
        self._passthrough_runner = passthrough_runner

    def _build_identity(self, command: RunPassthroughExecutionCommand) -> CallIdentity:
        return PassthroughCallIdentity(
            client=command.client,
            native_args_fingerprint=fingerprint_arguments(command.native_args),
        )

    def _run_client(self, command: RunPassthroughExecutionCommand) -> ClientRunResult:
        return self._passthrough_runner.run(command.client, command.native_args)

    def _execution_kind(self) -> ExecutionKind:
        return ExecutionKind.LOCAL_PASSTHROUGH

    def _journal_fields(self, command: RunPassthroughExecutionCommand) -> Tuple[str, str, str]:
        # A passthrough has no modelled model/effort — only the client is known.
        return command.client, "", ""
