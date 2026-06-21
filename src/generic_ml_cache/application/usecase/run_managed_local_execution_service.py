# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunManagedLocalExecutionService."""

from __future__ import annotations

from typing import Tuple

from generic_ml_cache.application.domain.model.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.client_run_request import ClientRunRequest
from generic_ml_cache.application.domain.model.client_run_result import ClientRunResult
from generic_ml_cache.application.domain.model.execution_kind import ExecutionKind
from generic_ml_cache.application.port.inbound.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)
from generic_ml_cache.application.port.inbound.run_managed_local_execution_use_case import (
    RunManagedLocalExecutionUseCase,
)
from generic_ml_cache.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache.application.port.out.client_runner_port import ClientRunnerPort
from generic_ml_cache.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache.application.port.out.metrics_port import MetricsPort
from generic_ml_cache.application.usecase.cached_ml_execution_service import (
    CachedMlExecutionService,
)
from generic_ml_cache.application.usecase.call_identity_building import build_call_identity


class RunManagedLocalExecutionService(CachedMlExecutionService, RunManagedLocalExecutionUseCase):
    """Record-or-replay a fully managed local ML client call.

    Implements the inbound port over the shared cached-execution flow, supplying
    the managed specifics: fingerprint inputs to build the identity, launch the
    client in an isolated folder via the client runner, tag executions
    LOCAL_MANAGED, and treat allow-path folders as non-cacheable (unless
    scan-trust).
    """

    def __init__(
        self,
        file_fingerprint: FileFingerprintPort,
        client_runner: ClientRunnerPort,
        blob_store: BlobStorePort,
        repository: ExecutionRepositoryPort,
        metrics: MetricsPort,
    ) -> None:
        super().__init__(blob_store, repository, metrics)
        self._file_fingerprint = file_fingerprint
        self._client_runner = client_runner

    def _build_identity(self, command: RunManagedLocalExecutionCommand) -> CallIdentity:
        return build_call_identity(self._file_fingerprint, command)

    def _run_client(self, command: RunManagedLocalExecutionCommand) -> ClientRunResult:
        return self._client_runner.run(self._build_client_run_request(command))

    def _execution_kind(self) -> ExecutionKind:
        return ExecutionKind.LOCAL_MANAGED

    def _journal_fields(self, command: RunManagedLocalExecutionCommand) -> Tuple[str, str, str]:
        return command.client, command.model, command.effort

    def _is_uncacheable(self, command: RunManagedLocalExecutionCommand) -> bool:
        return command.is_uncacheable

    @staticmethod
    def _build_client_run_request(command: RunManagedLocalExecutionCommand) -> ClientRunRequest:
        # The one allowed self-less method (AGENTS §6): the inbound-command ->
        # outbound-port-DTO boundary mapping, which is the use case's own job.
        return ClientRunRequest(
            client=command.client,
            model=command.model,
            effort=command.effort,
            context=command.context,
            prompt=command.prompt,
            user_system_prompt=command.user_system_prompt,
            input_file_paths=command.input_file_paths,
            allow_paths=command.allow_paths,
            client_args=command.client_args,
            grants=frozenset(command.grants),
        )
