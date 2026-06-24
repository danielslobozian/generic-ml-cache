# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlExecutionService — unified record-or-replay for managed, API, and passthrough runs."""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.ml_execution import normalize_tags
from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.application.usecase.cached_ml_execution_service import (
    CachedMlExecutionService,
)
from generic_ml_cache_core.application.usecase.call_identity_building import build_call_identity
from generic_ml_cache_core.common.checksum import fingerprint_arguments, text_checksum


class RunMlExecutionService(CachedMlExecutionService, RunMlExecutionUseCase):
    """Record-or-replay any ML execution — managed local, API, or passthrough.

    Dispatches to the right runner based on ``command.execution_kind`` using a
    runner map injected at construction time. LOCAL_MANAGED goes through the
    client runner (subprocess); API goes through the REST adapter; LOCAL_PASSTHROUGH
    forwards native_args verbatim to the passthrough runner. Identity, journaling,
    artifact storage, and the cache protocol are handled once by the shared base.
    """

    def __init__(
        self,
        file_fingerprint: FileFingerprintPort,
        runners: Dict[ExecutionKind, MlRunnerPort],
        blob_store: BlobStorePort,
        repository: ExecutionRepositoryPort,
        metrics: MetricsPort,
    ) -> None:
        super().__init__(blob_store, repository, metrics)
        self._file_fingerprint = file_fingerprint
        self._runners = runners

    def _build_identity(self, command: RunMlExecutionCommand) -> CallIdentity:
        if command.execution_kind is ExecutionKind.LOCAL_MANAGED:
            return build_call_identity(self._file_fingerprint, command)
        if command.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH:
            return PassthroughCallIdentity(
                client=command.client,
                native_args_fingerprint=fingerprint_arguments(command.native_args),
            )
        return ApiCallIdentity(
            provider=command.client,
            model=command.model,
            context_fingerprint=text_checksum(command.context),
            prompt_fingerprint=text_checksum(command.prompt),
            system_fingerprint=(
                text_checksum(command.user_system_prompt) if command.user_system_prompt else None
            ),
            effort=command.effort,
        )

    def _run_client(self, command: RunMlExecutionCommand) -> ClientRunResult:
        runner = self._runners.get(command.execution_kind)
        if runner is None:
            raise RuntimeError(
                f"No runner registered for {command.execution_kind!r}; "
                "pass client= to build_use_cases or wire a runner for this kind"
            )
        if command.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH:
            request = MlRequest(
                model="",
                effort="",
                context="",
                prompt="",
                native_args=list(command.native_args),
            )
        else:
            request = MlRequest(
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
        return runner.run(request)

    def _execution_kind(self, command: RunMlExecutionCommand) -> ExecutionKind:
        return command.execution_kind

    def _journal_fields(self, command: RunMlExecutionCommand) -> Tuple[str, str, str]:
        if command.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH:
            return command.client, "", ""
        return command.client, command.model, command.effort

    def _is_uncacheable(self, command: RunMlExecutionCommand) -> bool:
        return command.is_uncacheable

    def _execution_tags(self, command: RunMlExecutionCommand) -> List[str]:
        return normalize_tags(command.tags)

    def _input_parts(
        self, command: RunMlExecutionCommand
    ) -> List[Tuple[ArtifactType, Optional[str], bytes]]:
        if command.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH:
            payload = json.dumps(list(command.native_args))
            return [(ArtifactType.INPUT_ARGS, None, payload.encode("utf-8"))]
        parts: List[Tuple[ArtifactType, Optional[str], bytes]] = []
        if command.context:
            parts.append((ArtifactType.INPUT_CONTEXT, None, command.context.encode("utf-8")))
        parts.append((ArtifactType.INPUT_PROMPT, None, command.prompt.encode("utf-8")))
        if command.user_system_prompt:
            parts.append(
                (ArtifactType.INPUT_SYSTEM, None, command.user_system_prompt.encode("utf-8"))
            )
        return parts
