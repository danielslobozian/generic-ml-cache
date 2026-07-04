# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: run and alias commands — resolve, execute, and relay cached ML calls."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.grants import GRANTS
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.common.errors import (
    CacheError,
    CacheMiss,
    EncryptionTokenRequired,
    RunInterrupted,
    UnknownClient,
    WrongEncryptionToken,
)

from generic_ml_cache_cli import async_jobs, config
from generic_ml_cache_cli._compose import build_use_cases, get_encryption_state
from generic_ml_cache_cli.composition import (
    db_conn_factory,
    make_diag,
    read_text_arg,
    resolve_allow_paths,
    resolve_input_file_paths,
    resolve_session,
    resolve_token,
)
from generic_ml_cache_cli.discovery import execution_kind_for
from generic_ml_cache_cli.presenters.shared import (
    apply_output_files,
    artifact_text,
    run_exit_code,
)

#: capabilities a caller may open with --grant, sourced from the core domain
#: vocabulary so the CLI choices, the help, and what the adapters implement can
#: never drift.
GRANT_CHOICES: list[str] = list(GRANTS)
GRANT_HELP = (
    "open a capability for the client -- enablement, not restriction. One of "
    "{net, read, write, shell, web-search}: net reaches the web, read/write/shell "
    "widen file and command access, web-search enables the search tool. Part of "
    "the key (a granted call is its own execution) and cacheable like any call; use "
    "--force for a live re-fetch. Repeatable."
)


def _resolve_cache_mode(
    args: argparse.Namespace, settings: Mapping[str, tuple[object, str]]
) -> CacheMode:
    """The cache mode for a run: --offline / --force are explicit flags and win over
    the resolved (config/env/default) mode. Shared by managed `run` and `alias`."""
    if args.offline:
        return CacheMode.OFFLINE
    if args.force:
        return CacheMode.REFRESH
    return CacheMode(str(settings["mode"][0]))


def _resolve_managed_run(
    args: argparse.Namespace,
) -> tuple[dict[str, object], Path, str | None]:
    """Resolve a managed run into a JSON-serializable spec plus its run context.

    Returns ``(spec, store_root, token)``. The spec is the run fully resolved (prompt /
    context / system text, absolute paths, resolved mode / persist / timeout / executable),
    so it can drive a sync run *or* be written to a detached job's spec.json and replayed by
    the worker. Raises ConfigError."""
    context = read_text_arg(args.context, args.context_file, "context")
    prompt = read_text_arg(args.prompt, args.prompt_file, "prompt")
    if not prompt:
        raise SystemExit("error: a non-empty --prompt or --prompt-file is required")
    system_prompt = (
        read_text_arg(args.system_prompt, args.system_prompt_file, "system-prompt") or None
    )

    file_cfg = config.load()
    settings = config.resolve_settings(
        file_cfg, mode_flag=args.mode, persist_flag=args.persist, timeout_flag=args.timeout
    )
    cache_mode = _resolve_cache_mode(args, settings)

    spec: dict[str, object] = {
        "client": args.client,
        "model": args.model,
        "effort": args.effort,
        "context": context,
        "prompt": prompt,
        "system_prompt": system_prompt,
        "input_file_paths": resolve_input_file_paths(args.input_file),
        "allow_paths": resolve_allow_paths(args.allow_path),
        "trust_scan": bool(settings["trust_scan"][0]),
        "client_args": list(getattr(args, "client_arg", None) or []),
        "grants": list(getattr(args, "grant", None) or []),
        "cache_mode": cache_mode.value,
        "persistence_depth": str(settings["persist"][0]),
        "record_on_error": bool(args.record_on_error),
        "tags": list(getattr(args, "tag", None) or []),
        "session_id": resolve_session(args),
        "executable": config.executable_for(file_cfg, args.client, flag=args.executable),
        "timeout": config.resolved_timeout(settings),
        "max_size": config.resolved_max_size(settings),
        "adapters": sorted(file_cfg.adapters) if file_cfg.adapters is not None else None,
    }
    return spec, Path(str(settings["store"][0])), resolve_token(args)


def _spec_string(spec: dict[str, object], field_name: str) -> str:
    """A required string field of a run spec, validated at the JSON boundary."""
    field_value = spec.get(field_name)
    if not isinstance(field_value, str):
        raise ValueError(f"run spec field {field_name!r} must be a string: {field_value!r}")
    return field_value


def _spec_optional_string(spec: dict[str, object], field_name: str) -> str | None:
    """An optional string field of a run spec, validated at the JSON boundary."""
    field_value = spec.get(field_name)
    if field_value is not None and not isinstance(field_value, str):
        raise ValueError(f"run spec field {field_name!r} must be a string: {field_value!r}")
    return field_value


def _spec_strings(spec: dict[str, object], field_name: str) -> tuple[str, ...]:
    """A list-of-strings field of a run spec, validated at the JSON boundary."""
    field_value = spec.get(field_name)
    if not isinstance(field_value, list):
        raise ValueError(f"run spec field {field_name!r} must be a list: {field_value!r}")
    items: list[str] = []
    # Any list is a list of objects; the cast only widens the unknown item type.
    for item in cast("list[object]", field_value):
        if not isinstance(item, str):
            raise ValueError(f"run spec field {field_name!r} must hold strings: {item!r}")
        items.append(item)
    return tuple(items)


def spec_timeout(spec: dict[str, object]) -> float | None:
    """The run timeout in seconds from a spec, or ``None`` for no timeout."""
    field_value = spec.get("timeout")
    if field_value is None:
        return None
    if isinstance(field_value, bool) or not isinstance(field_value, (int, float)):
        raise ValueError(f"run spec field 'timeout' must be a number: {field_value!r}")
    return float(field_value)


def spec_max_size(spec: dict[str, object]) -> int | None:
    """The store size cap in bytes from a spec, or ``None`` when uncapped."""
    field_value = spec.get("max_size")
    if field_value is None:
        return None
    if isinstance(field_value, bool) or not isinstance(field_value, int):
        raise ValueError(f"run spec field 'max_size' must be an integer: {field_value!r}")
    return field_value


def spec_whitelist(spec: dict[str, object]) -> frozenset[str] | None:
    if spec.get("adapters") is None:
        return None
    return frozenset(_spec_strings(spec, "adapters"))


def command_from_spec(spec: dict[str, object]) -> RunMlExecutionCommand:
    client = _spec_string(spec, "client")
    return RunMlExecutionCommand(
        execution_kind=execution_kind_for(client, spec_whitelist(spec)),
        client=client,
        model=_spec_string(spec, "model"),
        effort=_spec_string(spec, "effort"),
        context=_spec_string(spec, "context"),
        prompt=_spec_string(spec, "prompt"),
        user_system_prompt=_spec_optional_string(spec, "system_prompt"),
        input_file_paths=tuple(
            str(Path(input_file_path))
            for input_file_path in _spec_strings(spec, "input_file_paths")
        ),
        allow_paths=tuple(
            str(Path(allow_path)) for allow_path in _spec_strings(spec, "allow_paths")
        ),
        scan_trust=bool(spec.get("trust_scan")),
        client_args=_spec_strings(spec, "client_args"),
        grants=_spec_strings(spec, "grants"),
        cache_mode=CacheMode(_spec_string(spec, "cache_mode")),
        persistence_depth=PersistenceDepth(_spec_string(spec, "persistence_depth")),
        record_on_error=bool(spec.get("record_on_error")),
        tags=_spec_strings(spec, "tags"),
        session_id=_spec_optional_string(spec, "session_id"),
    )


def spec_executable_override(spec: dict[str, object]) -> Callable[[str], str | None]:
    executable = _spec_optional_string(spec, "executable")
    return lambda client: executable


def run_cached_execution(
    execute: Callable[[], MlExecution],
) -> tuple[MlExecution | None, int | None]:
    """Run a wired ``execute()`` call, translating the failure modes shared by every
    cached command into ``(None, exit_code)``; on success returns ``(execution, None)``.

    Centralising the ladder keeps `run` and `alias` byte-identical on errors and means
    the rarely-hit branches (interrupt, timeout) are covered once, by the `run` tests."""
    try:
        return execute(), None
    except RunInterrupted as exc:
        # A requested stop, not a failure: nothing was recorded. Exit 130 is the
        # conventional "terminated by Ctrl-C".
        print(f"gmlc: {exc}", file=sys.stderr)
        return None, 130
    except subprocess.TimeoutExpired as exc:
        # The real call ran past --timeout and was killed before any record. Exit
        # 124 is the timeout(1) convention, distinct from miss (3) and error (4).
        print(
            f"gmlc: real call exceeded the {exc.timeout}s timeout and was killed; nothing recorded",
            file=sys.stderr,
        )
        return None, 124
    except CacheMiss as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return None, 3
    except (EncryptionTokenRequired, WrongEncryptionToken) as exc:
        print(f"gmlc: {exc} (set --token or GMLCACHE_TOKEN)", file=sys.stderr)
        return None, 4
    except UnknownClient as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return None, 4
    except CacheError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return None, 4


def relay_execution(execution: MlExecution) -> int:
    """Reproduce a (live or replayed) call's stdout, stderr and exit code exactly --
    the quiet-mode fidelity contract shared by `run` and `alias`."""
    sys.stdout.write(artifact_text(execution, ArtifactType.STDOUT))
    sys.stdout.flush()
    sys.stderr.write(artifact_text(execution, ArtifactType.STDERR))
    sys.stderr.flush()
    return run_exit_code(execution)


def _print_run_json(execution: MlExecution, command: RunMlExecutionCommand) -> int:
    import json

    usage = execution.token_usage
    files = [a for a in execution.artifacts if a.artifact_type is ArtifactType.OUTPUT_FILE]
    status = "success" if execution.execution_state is ExecutionState.SUCCESS else "failed"
    payload: dict[str, object] = {
        "status": status,
        "exit": run_exit_code(execution),
        "client": command.client,
        "model": command.model,
        "effort": command.effort,
        "files": len(files),
        "usage": usage.to_dict() if usage is not None else None,
        "stdout": artifact_text(execution, ArtifactType.STDOUT),
    }
    print(json.dumps(payload, indent=2))
    sys.stderr.write(artifact_text(execution, ArtifactType.STDERR))
    sys.stderr.flush()
    return run_exit_code(execution)


def _submit_detached(spec: dict[str, object], store_root: Path, token: str | None) -> int:
    """`run --detach`: write the job spec, spawn a detached worker, print the job id."""
    # On an encrypted store the worker needs the token to write its result. It is passed to the
    # worker through its environment (never to disk), the same exposure as a sync call holding
    # the token for the run's duration. So require it here, and gate on the store's actual
    # encryption state — not on whether a token happened to be passed.
    encrypted = get_encryption_state(store_root) is EncryptionState.ENCRYPTED
    if encrypted and token is None:
        print(
            "gmlc: the store is encrypted — provide the token to detach (--token or GMLCACHE_TOKEN)",
            file=sys.stderr,
        )
        return 4
    import secrets

    job_id = secrets.token_hex(8)
    store = async_jobs.JobStore(store_root)
    store.write_spec(job_id, spec)
    store.update_status(
        job_id,
        state=async_jobs.SUBMITTED,
        submitted_at=async_jobs.now(),
        client=spec["client"],
        model=spec["model"],
    )
    async_jobs.append_event(
        store.events_path(job_id), "submitted", client=spec["client"], model=spec["model"]
    )
    async_jobs.spawn_worker(store_root, job_id, token=token if encrypted else None)
    print(job_id)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from generic_ml_cache_core.common.errors import ConfigError

    try:
        spec, store_root, token = _resolve_managed_run(args)
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    if getattr(args, "detach", False):
        return _submit_detached(spec, store_root, token)

    try:
        command = command_from_spec(spec)
    except UnknownClient as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    execution, error = run_cached_execution(
        lambda: build_use_cases(
            db_conn_factory(store_root),
            store_root,
            spec_executable_override(spec),
            spec_timeout(spec),
            encryption_token=token,
            stream_path=getattr(args, "stream", None),
            client=command.client,
            max_size=spec_max_size(spec),
            whitelist=spec_whitelist(spec),
            diag=make_diag(args),
        ).run_ml.execute(command)
    )
    if error is not None:
        return error
    assert execution is not None

    # Materialise captured files into the cwd, exactly as the real client would.
    apply_output_files(execution, Path.cwd())

    if getattr(args, "json", False):
        return _print_run_json(execution, command)

    return relay_execution(execution)


def cmd_alias(args: argparse.Namespace) -> int:
    """`alias`: the thin native-client wrapper. Everything after the client is an
    opaque native-argument tail, forwarded verbatim and keyed (by fingerprint) as
    the cache identity. No isolation and no file capture -- a replay reproduces the
    native call's stdout/stderr/exit, exactly as the default `run` does in quiet mode.
    gmlcache's own options precede the client; the tail belongs to the native client."""
    from generic_ml_cache_core.common.errors import ConfigError

    native_args = list(getattr(args, "native_args", None) or [])
    # Accept an explicit `--` before the tail (`alias claude -- -p hi`) so a tail
    # that opens with a dash never has to fight argparse; it is not a native arg.
    if native_args and native_args[0] == "--":
        native_args = native_args[1:]

    try:
        file_cfg = config.load()
        settings = config.resolve_settings(
            file_cfg, mode_flag=args.mode, persist_flag=args.persist, timeout_flag=args.timeout
        )
        executable = config.executable_for(file_cfg, args.client, flag=args.executable)
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.LOCAL_PASSTHROUGH,
        client=args.client,
        model="",
        native_args=tuple(native_args),
        cache_mode=_resolve_cache_mode(args, settings),
        persistence_depth=PersistenceDepth(str(settings["persist"][0])),
        record_on_error=bool(args.record_on_error),
        session_id=resolve_session(args),
    )
    store_root = Path(str(settings["store"][0]))
    execution, error = run_cached_execution(
        lambda: build_use_cases(
            db_conn_factory(store_root),
            store_root,
            lambda _client: executable,
            config.resolved_timeout(settings),
            encryption_token=resolve_token(args),
            client=args.client,
            max_size=config.resolved_max_size(settings),
            whitelist=file_cfg.adapters,
            diag=make_diag(args),
        ).run_ml.execute(command)
    )
    if error is not None:
        return error
    assert execution is not None
    return relay_execution(execution)
