# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CliRuntime — the shared CLI-call engine every local client adapter composes.

This is the call *template* (Strategy/composition, not inheritance): it owns the
subprocess transport and per-run config, and runs the managed/passthrough call
against a client's translation hooks. It does NOT own workspace lifecycle or
artifact capture — those belong to the managed-execution use case in core.

A client adapter holds a CliRuntime and delegates ``execute_managed`` /
``execute_passthrough`` / ``stage_inputs`` / ``resolve_executable`` to it; the
runtime calls back into the client for the client-specific hooks (``build_argv``,
``parse_output``, ``stdin_payload``, ``config_home_env_var``, ``stream_event`` …).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.parsed_output import ParsedOutput
from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer
from generic_ml_cache_core.application.domain.model.run.managed_local_request import (
    ManagedLocalRequest,
)
from generic_ml_cache_core.application.domain.model.run.passthrough_request import (
    PassthroughRequest,
)
from generic_ml_cache_core.application.domain.model.run.workspace import Workspace
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.common.errors import ClientNotFound, RunTimedOut

from generic_ml_cache_adapters.adapter.outbound.client.cli_process_runner import CliProcessRunner
from generic_ml_cache_adapters.adapter.outbound.client.prime_directive import build_system_prompt
from generic_ml_cache_adapters.stream import StreamWriter

if TYPE_CHECKING:
    from generic_ml_cache_adapters.adapter.outbound.client.composed_local_client import (
        ComposedLocalClient,
    )

_TEXT_ENCODING = "utf-8"

HookResult = TypeVar("HookResult")


class CliRuntime:
    """Shared call engine composed by every local CLI client adapter."""

    def __init__(
        self,
        client: ComposedLocalClient,
        executable_override: str | None = None,
        timeout: float | None = None,
        stream_path: str | None = None,
    ) -> None:
        self._client = client
        self._executable_override = executable_override
        self._timeout = timeout
        self._stream_path = stream_path
        self._process = CliProcessRunner()

    def _hook(self, name: str, *args: object, default: HookResult) -> HookResult:
        """Call an optional client hook, falling back to a default when the client
        does not define it. Lets a minimal adapter implement only what it
        customizes (e.g. cursor has no stdin; the fake has no grants config).
        The caller's ``default`` fixes the expected result type; the hook itself
        is dynamic, so its result is trusted to match."""
        hook: Callable[..., HookResult] | None = getattr(self._client, name, None)
        return hook(*args) if callable(hook) else default

    # ------------------------------------------------------------------
    # Generic plumbing
    # ------------------------------------------------------------------

    def supports(self, kind: ExecutionKind) -> bool:
        return kind in (ExecutionKind.LOCAL_MANAGED, ExecutionKind.LOCAL_PASSTHROUGH)

    def version_argv(self, executable: str) -> list[str]:
        return [executable, "--version"]

    def models_argv(self, executable: str) -> list[str] | None:
        return None

    def resolve_executable(self, override: str | None) -> str:
        candidate = override or self._client.default_executable
        if any(sep in candidate for sep in ("/", "\\")):
            p = Path(candidate)
            if p.exists():
                return str(p)
            raise ClientNotFound(f"executable not found at {candidate!r}")
        found = shutil.which(candidate)
        if not found:
            raise ClientNotFound(
                f"could not find {candidate!r} on PATH; pass --executable to override"
            )
        return found

    # ------------------------------------------------------------------
    # Managed call template
    # ------------------------------------------------------------------

    def stage_inputs(self, request: ManagedLocalRequest, workspace: Workspace) -> None:
        system_prompt = build_system_prompt(request.user_system_prompt, request.allowed_read_paths)
        self._hook(
            "prepare",
            workspace.run_dir,
            request.context,
            request.prompt,
            system_prompt,
            default=None,
        )

    def execute_managed(self, request: ManagedLocalRequest, workspace: Workspace) -> ClientAnswer:
        client = self._client
        system_prompt = build_system_prompt(request.user_system_prompt, request.allowed_read_paths)
        executable = self.resolve_executable(self._executable_override)
        run_dir = workspace.run_dir
        config_home = workspace.config_home
        timeout = request.timeout if request.timeout is not None else self._timeout
        stream_path = request.stream_path or self._stream_path

        writer = StreamWriter(Path(stream_path)) if stream_path else None
        on_line: Callable[[str], None] | None = None
        if writer is not None:
            writer.event(
                "run.start",
                client=client.name,
                model=request.model,
                effort=request.effort or None,
                grants=",".join(sorted(set(request.grants))) or None,
            )

            def _emit(line: str) -> None:
                event: dict[str, str | None] | None = self._hook("stream_event", line, default=None)
                if not event:
                    return
                event_kind = event.pop("kind")
                if event_kind is not None:
                    writer.event(event_kind, **event)

            on_line = _emit

        try:
            argv = client.build_argv(
                executable,
                run_dir,
                request.model,
                request.effort,
                request.context,
                request.prompt,
                system_prompt,
                list(request.client_args),
                list(request.grants),
            )
            read_access_arguments: list[str] = self._hook(
                "read_access_argv", request.add_dir_paths, default=[]
            )
            grant_arguments: list[str] = self._hook("grant_argv", list(request.grants), default=[])
            argv += read_access_arguments
            argv += grant_arguments
            env_var: str | None = self._hook("config_home_env_var", default=None)
            run_env = {**os.environ, env_var: str(config_home)} if env_var else None
            stdin_payload: str | None = self._hook(
                "stdin_payload", request.context, request.prompt, system_prompt, default=None
            )

            try:
                stdout, stderr, returncode = self._process.run(
                    argv, run_dir, stdin_payload, timeout, run_env, on_line
                )
            except subprocess.TimeoutExpired as exc:
                # Translate the stdlib timeout at the client-run boundary (Y4/§10) so no
                # driver ever sees a raw subprocess type — this adapter surface only ever
                # raises CacheError. exc.timeout is the configured --timeout (a float).
                raise RunTimedOut(client=client.name, timeout_seconds=exc.timeout) from exc
            parsed: ParsedOutput = self._hook(
                "parse_output", stdout, default=ParsedOutput(text=stdout, usage=None)
            )

            if writer is not None:
                writer.event(
                    "run.end",
                    exit=returncode,
                    input_tokens=parsed.usage.input_tokens if parsed.usage else None,
                    output_tokens=parsed.usage.output_tokens if parsed.usage else None,
                )

            token_usage = (
                TokenUsage.from_dict(parsed.usage.to_dict()) if parsed.usage is not None else None
            )
            return ClientAnswer(
                exit_code=returncode,
                stdout=parsed.text,
                stderr=stderr,
                token_usage=token_usage,
            )
        finally:
            if writer is not None:
                writer.close()

    # ------------------------------------------------------------------
    # Passthrough call template
    # ------------------------------------------------------------------

    def execute_passthrough(self, request: PassthroughRequest) -> ClientAnswer:
        executable = self.resolve_executable(self._executable_override)
        timeout = request.timeout if request.timeout is not None else self._timeout
        try:
            completed = subprocess.run(
                [executable, *request.native_args],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            # Same boundary translation as the managed path (Y4/§10): the passthrough
            # relay must not leak a raw subprocess timeout to the driver either.
            raise RunTimedOut(client=self._client.name, timeout_seconds=exc.timeout) from exc
        return ClientAnswer(
            exit_code=completed.returncode,
            stdout=completed.stdout.decode(_TEXT_ENCODING, errors="replace"),
            stderr=completed.stderr.decode(_TEXT_ENCODING, errors="replace"),
        )


def wire_cli_client(
    adapter: ComposedLocalClient,
    executable_override: str | None = None,
    timeout: float | None = None,
    stream_path: str | None = None,
) -> CliRuntime:
    """Compose a CliRuntime into ``adapter`` by setting ``adapter.call``.

    This is the composition seam every standalone local client adapter calls from
    its ``__init__``. The adapter subclasses :class:`ComposedLocalClient`, which
    exposes the never-overridden LocalClientPort surface as delegations to this
    ``call`` runtime; the adapter itself defines only its client-specific hooks
    (``build_argv``, ``parse_output`` …) and its config knowledge. The call
    template lives once, in CliRuntime.
    """
    runtime = CliRuntime(adapter, executable_override, timeout, stream_path)
    adapter.call = runtime
    return runtime
