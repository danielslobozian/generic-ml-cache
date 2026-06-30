# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlExecutionService — unified record-or-replay for managed, API, and passthrough runs."""

from __future__ import annotations

import json
import time
from typing import Dict, List, Optional, Tuple, cast

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
from generic_ml_cache_core.application.domain.model.run.managed_local_request import (
    ManagedLocalRequest,
)
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.run.passthrough_request import (
    PassthroughRequest,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.client_config_port import ClientConfigPort
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.application.port.out.local_client_port import LocalClientPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.application.port.out.registered_adapter import RegisteredAdapter
from generic_ml_cache_core.application.port.out.workspace_port import WorkspacePort
from generic_ml_cache_core.application.usecase.cached_ml_execution_service import (
    CachedMlExecutionService,
)
from generic_ml_cache_core.application.usecase.call_identity_building import build_call_identity
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.common.checksum import fingerprint_arguments, text_checksum


class RunMlExecutionService(CachedMlExecutionService[RunMlExecutionCommand], RunMlExecutionUseCase):
    """Record-or-replay any ML execution — managed local, API, or passthrough.

    Two orthogonal axes drive a call. The **client name** (``command.client``)
    selects *which* adapter from the injected ``runners`` map; the **execution
    kind** (``command.execution_kind``) selects *how* it is invoked — a CLI
    adapter answers both LOCAL_MANAGED (isolated workspace owned here via the
    :class:`WorkspacePort`, artifacts captured) and LOCAL_PASSTHROUGH (a raw
    relay), while an API adapter answers API through :class:`MlRunnerPort`. A
    single-client driver (the CLI) injects a one-entry map; a multi-client driver
    (the daemon) injects one entry per client it serves. Identity, journaling,
    artifact storage, and the cache protocol are handled once by the shared base.
    """

    def __init__(
        self,
        file_fingerprint: FileFingerprintPort,
        runners: Dict[str, RegisteredAdapter],
        blob_store: BlobStorePort,
        repository: ExecutionRepositoryPort,
        metrics: MetricsPort,
        purge_service: Optional[PurgeService] = None,
        max_size: Optional[int] = None,
        workspace: Optional[WorkspacePort] = None,
        diag: Optional[DiagnosticsPort] = None,
    ) -> None:
        super().__init__(blob_store, repository, metrics, diag)
        self._file_fingerprint = file_fingerprint
        self._runners = runners
        self._purge = purge_service
        self._max_size = max_size
        self._workspace = workspace

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
        _t = time.perf_counter()
        runner = self._runners.get(command.client)
        if runner is None:
            if self._diag:
                self._diag.error(
                    "no runner registered for client",
                    client=command.client,
                    kind=str(command.execution_kind),
                )
            raise RuntimeError(
                f"No runner registered for client {command.client!r}; "
                "pass client= to build_use_cases or wire a runner for this client"
            )
        if self._diag:
            self._diag.debug(
                "invoking client",
                client=command.client,
                kind=str(command.execution_kind),
                model=command.model or "",
            )
        if command.execution_kind is ExecutionKind.LOCAL_MANAGED:
            # Core owns the workspace lifecycle and artifact capture; the adapter
            # only stages inputs and makes the call (translate request -> answer).
            result = self._run_managed(command, runner)
        elif command.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH:
            # The adapter makes the raw call; core packages it (no files).
            result = self._run_passthrough(command, runner)
        else:
            # API: the legacy MlRunnerPort.run path — a single REST call.
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
            result = cast(MlRunnerPort, runner).run(request)
        if self._diag:
            self._diag.debug(
                "invoking client EXIT",
                client=command.client,
                kind=str(command.execution_kind),
                model=command.model or "",
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
        return result

    def _run_managed(
        self, command: RunMlExecutionCommand, runner: RegisteredAdapter
    ) -> ClientRunResult:
        """Orchestrate one isolated managed run: prepare the workspace, let the
        client make its call, capture the generated files, and package the result.
        The client knows *how* (argv, config, parsing); core owns *the workspace*."""
        if self._workspace is None:
            raise RuntimeError("managed execution requires a WorkspacePort; none was injected")
        client = cast(LocalClientPort, runner)
        request = ManagedLocalRequest(
            model=command.model,
            effort=command.effort,
            context=command.context,
            prompt=command.prompt,
            user_system_prompt=command.user_system_prompt,
            allowed_read_paths=sorted([*command.input_file_paths, *command.allow_paths]),
            add_dir_paths=sorted(command.allow_paths),
            client_args=list(command.client_args),
            grants=frozenset(command.grants),
        )
        workspace = self._workspace.create()
        try:
            # A client that carries config knowledge (the grant file + credentials)
            # has its config materialized; one that does not (e.g. a bare runner)
            # is simply launched.
            if isinstance(runner, ClientConfigPort):
                self._workspace.write_config(
                    workspace, runner.build_grants_config_file(list(request.grants))
                )
                self._workspace.seed_credentials(workspace, runner.get_token_files())
            client.stage_inputs(request, workspace)
            baseline = self._workspace.snapshot(workspace.run_dir)
            answer = client.execute_managed(request, workspace)
            files = self._workspace.capture(workspace.run_dir, baseline)
        finally:
            self._workspace.dispose(workspace)
        return ClientRunResult(
            exit_code=answer.exit_code,
            stdout=answer.stdout,
            stderr=answer.stderr,
            files=files,
            token_usage=answer.token_usage,
        )

    def _run_passthrough(
        self, command: RunMlExecutionCommand, runner: RegisteredAdapter
    ) -> ClientRunResult:
        """Relay a native passthrough call through the client and package it. There
        is no workspace and no artifact capture — a passthrough never produces files."""
        client = cast(LocalClientPort, runner)
        answer = client.execute_passthrough(
            PassthroughRequest(native_args=list(command.native_args))
        )
        return ClientRunResult(
            exit_code=answer.exit_code,
            stdout=answer.stdout,
            stderr=answer.stderr,
            files=[],
            token_usage=answer.token_usage,
        )

    def _after_record(self, execution_key: str) -> None:
        if self._purge is not None and self._max_size is not None:
            self._purge.evict_to_quota(self._max_size)

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
