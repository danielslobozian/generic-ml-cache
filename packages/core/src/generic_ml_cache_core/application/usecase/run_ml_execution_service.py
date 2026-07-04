# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlExecutionService — unified record-or-replay for managed, API, and passthrough runs."""

from __future__ import annotations

import json
import time

from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.ml_execution import normalize_tags
from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.api_passthrough_call_identity import (
    ApiPassthroughCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)
from generic_ml_cache_core.application.domain.model.run.api_passthrough_request import (
    ApiPassthroughRequest,
)
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.managed_local_request import (
    ManagedLocalRequest,
)
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.run.passthrough_request import (
    PassthroughRequest,
)
from generic_ml_cache_core.application.port.inbound.purge.evict_to_quota_command import (
    EvictToQuotaCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.outbound.api_passthrough_runner_port import (
    ApiPassthroughRunnerPort,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.call_journal_ports import RecordCallEventPort
from generic_ml_cache_core.application.port.outbound.client_config_port import ClientConfigPort
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.file_fingerprint_port import (
    FileFingerprintPort,
)
from generic_ml_cache_core.application.port.outbound.managed_local_runner_port import (
    ManagedLocalRunnerPort,
)
from generic_ml_cache_core.application.port.outbound.ml_run_ports import (
    AnnotateMlRunPort,
    ReadMlRunPort,
    SaveMlRunPort,
)
from generic_ml_cache_core.application.port.outbound.ml_runner_port import MlRunnerPort
from generic_ml_cache_core.application.port.outbound.passthrough_local_runner_port import (
    PassthroughLocalRunnerPort,
)
from generic_ml_cache_core.application.port.outbound.registered_adapter_port import (
    RegisteredAdapterPort,
)
from generic_ml_cache_core.application.port.outbound.workspace_port import WorkspacePort
from generic_ml_cache_core.application.usecase.cached_ml_execution_service import (
    CachedMlExecutionService,
)
from generic_ml_cache_core.application.usecase.call_identity_building import build_call_identity
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.common.checksum import (
    file_content_fingerprint,
    fingerprint_arguments,
    text_checksum,
)
from generic_ml_cache_core.common.errors import UnknownClient, UnsupportedExecutionMode


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
        runners: dict[str, RegisteredAdapterPort],
        blob_store: BlobStorePort,
        save: SaveMlRunPort,
        read: ReadMlRunPort,
        annotate: AnnotateMlRunPort,
        record: RecordCallEventPort,
        purge_service: PurgeService | None = None,
        max_size: int | None = None,
        workspace: WorkspacePort | None = None,
        diag: DiagnosticsPort | None = None,
    ) -> None:
        super().__init__(blob_store, save, read, annotate, record, diag)
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
        if command.execution_kind is ExecutionKind.API_PASSTHROUGH:
            return ApiPassthroughCallIdentity(
                client=command.client,
                body_fingerprint=file_content_fingerprint(command.raw_body),
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
            raise UnknownClient(
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
        elif command.execution_kind is ExecutionKind.API_PASSTHROUGH:
            # The relay forwards the raw body verbatim and returns the wire response.
            result = self._run_api_passthrough(command, runner)
        else:
            result = self._run_api(command, runner)
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
        self, command: RunMlExecutionCommand, runner: RegisteredAdapterPort
    ) -> ClientRunResult:
        """Orchestrate one isolated managed run: prepare the workspace, let the
        client make its call, capture the generated files, and package the result.
        The client knows *how* (argv, config, parsing); core owns *the workspace*."""
        if self._workspace is None:
            raise RuntimeError("managed execution requires a WorkspacePort; none was injected")
        if not isinstance(runner, ManagedLocalRunnerPort):
            raise UnsupportedExecutionMode(
                f"client {command.client!r} does not support managed local execution"
            )
        client = runner
        request = ManagedLocalRequest(
            model=command.model,
            effort=command.effort,
            context=command.context,
            prompt=command.prompt,
            user_system_prompt=command.user_system_prompt,
            allowed_read_paths=tuple(sorted([*command.input_file_paths, *command.allow_paths])),
            add_dir_paths=tuple(sorted(command.allow_paths)),
            client_args=tuple(command.client_args),
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
            files=tuple(files),
            token_usage=answer.token_usage,
        )

    def _run_passthrough(
        self, command: RunMlExecutionCommand, runner: RegisteredAdapterPort
    ) -> ClientRunResult:
        """Relay a native passthrough call through the client and package it. There
        is no workspace and no artifact capture — a passthrough never produces files."""
        if not isinstance(runner, PassthroughLocalRunnerPort):
            raise UnsupportedExecutionMode(
                f"client {command.client!r} does not support passthrough local execution"
            )
        client = runner
        answer = client.execute_passthrough(
            PassthroughRequest(native_args=tuple(command.native_args))
        )
        return ClientRunResult(
            exit_code=answer.exit_code,
            stdout=answer.stdout,
            stderr=answer.stderr,
            files=(),
            token_usage=answer.token_usage,
        )

    def _run_api(
        self, command: RunMlExecutionCommand, runner: RegisteredAdapterPort
    ) -> ClientRunResult:
        """The structured API path — a single REST call through MlRunnerPort. Check
        the capability before use so a miswired registry (an adapter that is not
        actually an MlRunnerPort) yields a named error, not an AttributeError from a
        blind cast (W18)."""
        if not isinstance(runner, MlRunnerPort):
            raise UnsupportedExecutionMode(
                f"client {command.client!r} does not support "
                f"{command.execution_kind.value} execution"
            )
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

    def _run_api_passthrough(
        self, command: RunMlExecutionCommand, runner: RegisteredAdapterPort
    ) -> ClientRunResult:
        """Relay the raw request bytes through the API-passthrough adapter and
        package the verbatim wire response as a single stdout blob (no files). The
        adapter maps the upstream HTTP status onto the answer's exit code, so a 200
        becomes a servable success and any other status a non-cached failure that is
        still returned. Check the capability before use so a miswired registry yields
        a named error, not an AttributeError (W18)."""
        if not isinstance(runner, ApiPassthroughRunnerPort):
            raise UnsupportedExecutionMode(
                f"client {command.client!r} does not support API-passthrough execution"
            )
        client = runner
        answer = client.execute_api_passthrough(
            ApiPassthroughRequest(
                raw_body=command.raw_body, forward_headers=dict(command.forward_headers)
            )
        )
        return ClientRunResult(
            exit_code=answer.exit_code,
            stdout=answer.stdout,
            stderr=answer.stderr,
            files=(),
            token_usage=answer.token_usage,
        )

    def _after_record(self, execution_key: str) -> None:
        if self._purge is not None and self._max_size is not None:
            self._purge.evict_to_quota(EvictToQuotaCommand(self._max_size))

    def _execution_kind(self, command: RunMlExecutionCommand) -> ExecutionKind:
        return command.execution_kind

    def _journal_fields(self, command: RunMlExecutionCommand) -> tuple[str, str, str]:
        if command.execution_kind in (
            ExecutionKind.LOCAL_PASSTHROUGH,
            ExecutionKind.API_PASSTHROUGH,
        ):
            return command.client, "", ""
        return command.client, command.model, command.effort

    def _is_uncacheable(self, command: RunMlExecutionCommand) -> bool:
        return command.is_uncacheable

    def _execution_tags(self, command: RunMlExecutionCommand) -> list[str]:
        return normalize_tags(command.tags)

    def _input_parts(
        self, command: RunMlExecutionCommand
    ) -> list[tuple[ArtifactType, str | None, bytes]]:
        if command.execution_kind is ExecutionKind.LOCAL_PASSTHROUGH:
            payload = json.dumps(list(command.native_args))
            return [(ArtifactType.INPUT_ARGS, None, payload.encode("utf-8"))]
        if command.execution_kind is ExecutionKind.API_PASSTHROUGH:
            return [(ArtifactType.INPUT_MESSAGES, None, command.raw_body)]
        parts: list[tuple[ArtifactType, str | None, bytes]] = []
        if command.context:
            parts.append((ArtifactType.INPUT_CONTEXT, None, command.context.encode("utf-8")))
        parts.append((ArtifactType.INPUT_PROMPT, None, command.prompt.encode("utf-8")))
        if command.user_system_prompt:
            parts.append(
                (ArtifactType.INPUT_SYSTEM, None, command.user_system_prompt.encode("utf-8"))
            )
        return parts
