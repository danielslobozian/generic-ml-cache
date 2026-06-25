# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
# PYTHON_ARGCOMPLETE_OK
"""Command-line interface for generic-ml-cache.

    gmlcache run     -- resolve a request (record on miss, replay on hit)
    gmlcache doctor  -- report which configured clients are present (advisory)
    gmlcache models  -- list a client's available models (advisory; relayed)
    gmlcache status  -- show the resolved configuration and where it came from
    gmlcache init    -- create the config file in the default location (if absent)
    gmlcache inspect -- pretty-print a stored execution

Replay fidelity: in the default (quiet) mode, ``run`` reproduces the client's
stdout, stderr and exit code exactly. Cache diagnostics appear only with
``-v/--verbose`` and are written to stderr with a ``gmlc:`` prefix, which by
design breaks byte-exact stderr fidelity -- use quiet mode when that matters.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

try:
    import argcomplete
except ImportError:  # completion is a convenience; never let its absence break the CLI
    argcomplete = None

from generic_ml_cache_core.adapter.inbound.composition import (
    build_use_cases,
    resolve_execution_kind,
)
from generic_ml_cache_core.adapter.out.crypto.filesystem_encryption_manifest_store import (
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_core.adapter.out.crypto.store_encryptor import StoreEncryptor
from generic_ml_cache_core.adapter.out.persistence.sqlite_store_lock import SqliteStoreLock
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)
from generic_ml_cache_core.adapter.out.api.api_registry import registered_api_names
from generic_ml_cache_core.adapter.out.client.registry import registered_names
from generic_ml_cache_core.application.domain.model.execution.artifact import (
    INPUT_ARTIFACT_TYPES,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.usecase.session_report import build_session_report
from generic_ml_cache_cli import async_jobs
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.out.base import ClientAdapter
from generic_ml_cache_core.common.errors import (
    CacheError,
    CacheMiss,
    ConfigError,
    EncryptionStateError,
    EncryptionTokenRequired,
    RunInterrupted,
    StoreLocked,
    WrongEncryptionToken,
)

from . import __version__, config

#: capabilities a caller may open with --grant, sourced from the adapter seam so
#: the CLI choices, the help, and what the adapters implement can never drift.
GRANT_CHOICES: List[str] = list(ClientAdapter.GRANTS)
_GRANT_HELP = (
    "open a capability for the client -- enablement, not restriction. One of "
    "{net, read, write, shell, web-search}: net reaches the web, read/write/shell "
    "widen file and command access, web-search enables the search tool. Part of "
    "the key (a granted call is its own execution) and cacheable like any call; use "
    "--force for a live re-fetch. Repeatable."
)


def _read_text_arg(inline: Optional[str], path: Optional[str], name: str) -> str:
    if inline is not None and path is not None:
        raise SystemExit(f"error: pass only one of --{name} / --{name}-file")
    if path is not None:
        return Path(path).read_text(encoding="utf-8")
    return inline if inline is not None else ""


def _resolve_input_file_paths(raw_paths) -> List[str]:
    """Declared input files, resolved to absolute (path-sensitive keying). The
    use case's fingerprint adapter validates readability and raises on a bad one."""
    return [str(Path(raw).resolve()) for raw in (raw_paths or [])]


def _resolve_allow_paths(raw_paths) -> List[str]:
    """Declared scan folders: validated directories, normalised to absolute."""
    resolved: List[str] = []
    for raw in raw_paths or []:
        path = Path(raw)
        if not path.is_dir():
            raise SystemExit(f"error: allow-path is not a directory: {raw}")
        resolved.append(str(path.resolve()))
    return resolved


def _artifact_text(execution: MlExecution, artifact_type: ArtifactType) -> str:
    for artifact in execution.artifacts:
        if artifact.artifact_type is artifact_type:
            return (artifact.content or b"").decode("utf-8", errors="replace")
    return ""


def _stored_artifact_text(execution: MlExecution, blob_store, artifact_type: ArtifactType) -> str:
    """Like ``_artifact_text``, but hydrates the bytes from the blob store when a
    stored execution carries only artifact metadata (``content is None``)."""
    for artifact in execution.artifacts:
        if artifact.artifact_type is artifact_type:
            content = artifact.content
            if content is None:
                content = blob_store.get(artifact.blob_key)
            return (content or b"").decode("utf-8", errors="replace")
    return ""


def _run_exit_code(execution: MlExecution) -> int:
    if execution.failure is not None and execution.failure.exit_code is not None:
        return execution.failure.exit_code
    return 0 if execution.execution_state is ExecutionState.SUCCESS else 1


def _apply_output_files(execution: MlExecution, output_dir: Path) -> None:
    """Write captured output files into ``output_dir``, mirroring a real client.
    Any attempt to escape the directory (``..`` / absolute) is refused."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir.resolve()
    for artifact in execution.artifacts:
        if artifact.artifact_type is not ArtifactType.OUTPUT_FILE or artifact.name is None:
            continue
        target = (output_dir / Path(artifact.name)).resolve()
        if base != target and base not in target.parents:
            raise ValueError(f"refusing to write outside output dir: {artifact.name!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content or b"")


def _print_run_json(execution: MlExecution, command: RunMlExecutionCommand) -> int:
    import json

    usage = execution.token_usage
    files = [a for a in execution.artifacts if a.artifact_type is ArtifactType.OUTPUT_FILE]
    status = "success" if execution.execution_state is ExecutionState.SUCCESS else "failed"
    payload = {
        "status": status,
        "exit": _run_exit_code(execution),
        "client": command.client,
        "model": command.model,
        "effort": command.effort,
        "files": len(files),
        "usage": usage.to_dict() if usage is not None else None,
        "stdout": _artifact_text(execution, ArtifactType.STDOUT),
    }
    print(json.dumps(payload, indent=2))
    sys.stderr.write(_artifact_text(execution, ArtifactType.STDERR))
    sys.stderr.flush()
    return _run_exit_code(execution)


def _resolve_managed_run(args: argparse.Namespace):
    """Resolve a managed run into a JSON-serializable spec plus its run context.

    Returns ``(spec, store_root, token)``. The spec is the run fully resolved (prompt /
    context / system text, absolute paths, resolved mode / persist / timeout / executable),
    so it can drive a sync run *or* be written to a detached job's spec.json and replayed by
    the worker. Raises ConfigError."""
    context = _read_text_arg(args.context, args.context_file, "context")
    prompt = _read_text_arg(args.prompt, args.prompt_file, "prompt")
    if not prompt:
        raise SystemExit("error: a non-empty --prompt or --prompt-file is required")
    system_prompt = (
        _read_text_arg(args.system_prompt, args.system_prompt_file, "system-prompt") or None
    )

    file_cfg = config.load()
    settings = config.resolve_settings(
        file_cfg, mode_flag=args.mode, persist_flag=args.persist, timeout_flag=args.timeout
    )
    cache_mode = _resolve_cache_mode(args, settings)

    spec = {
        "client": args.client,
        "model": args.model,
        "effort": args.effort,
        "context": context,
        "prompt": prompt,
        "system_prompt": system_prompt,
        "input_file_paths": _resolve_input_file_paths(args.input_file),
        "allow_paths": _resolve_allow_paths(args.allow_path),
        "trust_scan": bool(settings["trust_scan"][0]),
        "client_args": list(getattr(args, "client_arg", None) or []),
        "grants": list(getattr(args, "grant", None) or []),
        "cache_mode": cache_mode.value,
        "persistence_depth": str(settings["persist"][0]),
        "record_on_error": bool(args.record_on_error),
        "tags": list(getattr(args, "tag", None) or []),
        "session_id": _resolve_session(args),
        "executable": config.executable_for(file_cfg, args.client, flag=args.executable),
        "timeout": settings["timeout"][0],
        "max_size": settings["max_size"][0],
    }
    return spec, Path(str(settings["store"][0])), _resolve_token(args)


def _command_from_spec(spec: dict) -> RunMlExecutionCommand:
    return RunMlExecutionCommand(
        execution_kind=resolve_execution_kind(spec["client"]),
        client=spec["client"],
        model=spec["model"],
        effort=spec["effort"],
        context=spec["context"],
        prompt=spec["prompt"],
        user_system_prompt=spec["system_prompt"],
        input_file_paths=[Path(p) for p in spec["input_file_paths"]],
        allow_paths=[Path(p) for p in spec["allow_paths"]],
        scan_trust=spec["trust_scan"],
        client_args=list(spec["client_args"]),
        grants=list(spec["grants"]),
        cache_mode=CacheMode(spec["cache_mode"]),
        persistence_depth=PersistenceDepth(spec["persistence_depth"]),
        record_on_error=spec["record_on_error"],
        tags=list(spec["tags"]),
        session_id=spec["session_id"],
    )


def _spec_executable_override(spec: dict):
    executable = spec.get("executable")
    return lambda client: executable


def _resolve_cache_mode(args: argparse.Namespace, settings: dict) -> CacheMode:
    """The cache mode for a run: --offline / --force are explicit flags and win over
    the resolved (config/env/default) mode. Shared by managed `run` and `alias`."""
    if args.offline:
        return CacheMode.OFFLINE
    if args.force:
        return CacheMode.REFRESH
    return CacheMode(str(settings["mode"][0]))


def _run_cached_execution(execute):
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
    except CacheError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return None, 4


def _relay_execution(execution: MlExecution) -> int:
    """Reproduce a (live or replayed) call's stdout, stderr and exit code exactly --
    the quiet-mode fidelity contract shared by `run` and `alias`."""
    sys.stdout.write(_artifact_text(execution, ArtifactType.STDOUT))
    sys.stdout.flush()
    sys.stderr.write(_artifact_text(execution, ArtifactType.STDERR))
    sys.stderr.flush()
    return _run_exit_code(execution)


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        spec, store_root, token = _resolve_managed_run(args)
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    if getattr(args, "detach", False):
        return _submit_detached(spec, store_root, token)

    command = _command_from_spec(spec)
    execution, error = _run_cached_execution(
        lambda: build_use_cases(
            store_root,
            _spec_executable_override(spec),
            spec["timeout"],
            encryption_token=token,
            stream_path=getattr(args, "stream", None),
            client=spec["client"],
            max_size=spec.get("max_size"),
        ).run_ml.execute(command)
    )
    if error is not None:
        return error

    # Materialise captured files into the cwd, exactly as the real client would.
    _apply_output_files(execution, Path.cwd())

    if getattr(args, "json", False):
        return _print_run_json(execution, command)

    return _relay_execution(execution)


def _cmd_alias(args: argparse.Namespace) -> int:
    """`alias`: the thin native-client wrapper. Everything after the client is an
    opaque native-argument tail, forwarded verbatim and keyed (by fingerprint) as
    the cache identity. No isolation and no file capture -- a replay reproduces the
    native call's stdout/stderr/exit, exactly as the default `run` does in quiet mode.
    gmlcache's own options precede the client; the tail belongs to the native client."""
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
        native_args=native_args,
        cache_mode=_resolve_cache_mode(args, settings),
        persistence_depth=PersistenceDepth(str(settings["persist"][0])),
        record_on_error=bool(args.record_on_error),
        session_id=_resolve_session(args),
    )
    store_root = Path(str(settings["store"][0]))
    execution, error = _run_cached_execution(
        lambda: build_use_cases(
            store_root,
            lambda _client: executable,
            settings["timeout"][0],
            encryption_token=_resolve_token(args),
            client=args.client,
            max_size=settings["max_size"][0],
        ).run_ml.execute(command)
    )
    if error is not None:
        return error
    return _relay_execution(execution)


def _submit_detached(spec: dict, store_root: Path, token: Optional[str]) -> int:
    """`run --detach`: write the job spec, spawn a detached worker, print the job id."""
    # On an encrypted store the worker needs the token to write its result. It is passed to the
    # worker through its environment (never to disk), the same exposure as a sync call holding
    # the token for the run's duration. So require it here, and gate on the store's actual
    # encryption state — not on whether a token happened to be passed.
    encrypted = FilesystemEncryptionManifestStore(store_root).state() is EncryptionState.ENCRYPTED
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


def _cmd_worker(args: argparse.Namespace) -> int:
    """Hidden: the detached worker. Run the job's managed execution while holding its
    liveness lock, recording the outcome to status.json. Never writes to the cwd."""
    store_root = Path(args.store_root)
    store = async_jobs.JobStore(store_root)
    job_id = args.job_id
    try:
        spec = store.read_spec(job_id)
    except (OSError, ValueError):
        return 1
    try:
        with async_jobs.hold_job_lock(store.lock_path(job_id)):
            events = store.events_path(job_id)
            store.update_status(job_id, state=async_jobs.RUNNING, started_at=async_jobs.now())
            async_jobs.append_event(events, "running", client=spec["client"], model=spec["model"])
            try:
                command = _command_from_spec(spec)
                # On an encrypted store the token arrives via the environment (set by the
                # spawner), never from disk; a public store ignores it.
                token = os.environ.get("GMLCACHE_TOKEN") or None
                wired = build_use_cases(
                    store_root,
                    _spec_executable_override(spec),
                    spec["timeout"],
                    encryption_token=token,
                    stream_path=str(events),  # client live events land in the job's log
                    client=spec["client"],
                    max_size=spec.get("max_size"),
                )
                execution = wired.run_ml.execute(command)
            except Exception as exc:
                store.update_status(
                    job_id, state=async_jobs.FAILED, ended_at=async_jobs.now(), error=str(exc)
                )
                async_jobs.append_event(events, "failed", error=str(exc))
                return 1
            key = execution.call_identity.generate_key()
            exit_code = _run_exit_code(execution)
            store.update_status(
                job_id,
                state=async_jobs.SUCCEEDED,
                ended_at=async_jobs.now(),
                execution_key=key,
                exit_code=exit_code,
            )
            async_jobs.append_event(events, "succeeded", execution_key=key, exit_code=exit_code)
            return 0
    except StoreLocked:
        return 1


# -- execution (detached job) readers -----------------------------------------


def _state_style(state: str):
    # Built at call time: the ANSI palette constants are defined later in the module.
    return {
        async_jobs.RUNNING: (_TEAL,),
        async_jobs.SUBMITTED: (_GREY,),
        async_jobs.SUCCEEDED: (_GREEN,),
        async_jobs.FAILED: (_AMBER,),
        async_jobs.INTERRUPTED: (_AMBER,),
    }.get(state, ())


def _job_state(store: "async_jobs.JobStore", job_id: str):
    """(status dict or None, derived state) for a job, applying the liveness probe."""
    status = store.read_status(job_id)
    held = async_jobs.job_lock_held(store.lock_path(job_id))
    return status, async_jobs.derived_state(status, held)


def _cmd_execution_status(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    store = async_jobs.JobStore(store_root)
    if not store.exists(args.job_id):
        print(f"gmlc: no such job {args.job_id!r}", file=sys.stderr)
        return 4
    status, state = _job_state(store, args.job_id)
    status = status or {}

    if args.json:
        import json

        print(json.dumps({**status, "state": state}, indent=2))
        return 0

    print(f"job        : {args.job_id}")
    print(f"state      : {_paint(state, *_state_style(state))}")
    if status.get("client"):
        print(f"client     : {status['client']} / {status.get('model', '')}")
    for label, field in (
        ("submitted", "submitted_at"),
        ("started", "started_at"),
        ("ended", "ended_at"),
    ):
        if status.get(field):
            print(f"{label:<10} : {status[field]}")
    if status.get("exit_code") is not None:
        print(f"exit       : {status['exit_code']}")
    if state == async_jobs.SUCCEEDED and status.get("execution_key"):
        print(
            f"result     : {status['execution_key'][:12]}  (gmlcache execution result {args.job_id})"
        )
    if state == async_jobs.INTERRUPTED:
        print("note       : the worker vanished before finishing (lock released, no result)")
    elif state == async_jobs.FAILED and status.get("error"):
        print(f"error      : {status['error']}")
    return 0


def _cmd_execution_result(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    store = async_jobs.JobStore(store_root)
    if not store.exists(args.job_id):
        print(f"gmlc: no such job {args.job_id!r}", file=sys.stderr)
        return 4
    status, state = _job_state(store, args.job_id)
    status = status or {}

    if state in (async_jobs.SUBMITTED, async_jobs.RUNNING):
        print(f"gmlc: job {args.job_id} is still {state}; not finished yet", file=sys.stderr)
        return 75  # EX_TEMPFAIL: "try again later"
    if state == async_jobs.INTERRUPTED:
        print(
            f"gmlc: job {args.job_id} was interrupted — the worker vanished before finishing",
            file=sys.stderr,
        )
        return 1
    if state != async_jobs.SUCCEEDED:
        print(
            f"gmlc: job {args.job_id} failed: {status.get('error', '(no detail)')}", file=sys.stderr
        )
        return 1

    key = status.get("execution_key")
    if not key:
        print(f"gmlc: job {args.job_id} has no stored result", file=sys.stderr)
        return 4
    token = _resolve_token(args)
    try:
        wired = build_use_cases(store_root, encryption_token=token)
        execution = wired.repository.find_current(key)
        if execution is None:
            print(
                f"gmlc: job {args.job_id} has no stored result (was the cache pruned?)",
                file=sys.stderr,
            )
            return 4
        out = _stored_artifact_text(execution, wired.blob_store, ArtifactType.STDOUT)
        err = _stored_artifact_text(execution, wired.blob_store, ArtifactType.STDERR)
    except (EncryptionTokenRequired, WrongEncryptionToken) as exc:
        print(f"gmlc: {exc} (set --token or GMLCACHE_TOKEN)", file=sys.stderr)
        return 4
    sys.stdout.write(out)
    sys.stdout.flush()
    sys.stderr.write(err)
    sys.stderr.flush()
    return int(status.get("exit_code") or 0)


def _cmd_execution_list(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    store = async_jobs.JobStore(store_root)
    rows = []
    for job_id in store.list_ids():
        status, state = _job_state(store, job_id)
        status = status or {}
        rows.append(
            (
                job_id,
                state,
                status.get("client", ""),
                status.get("model", ""),
                status.get("submitted_at", ""),
            )
        )

    if args.json:
        import json

        print(
            json.dumps(
                [
                    {"job": j, "state": s, "client": c, "model": m, "submitted_at": t}
                    for j, s, c, m, t in rows
                ],
                indent=2,
            )
        )
        return 0
    if not rows:
        print("no detached jobs")
        return 0
    for job_id, state, client, model, submitted in rows:
        painted = _paint(f"{state:<11}", *_state_style(state))
        print(f"{job_id}  {painted} {client}/{model}  {submitted}")
    return 0


def _print_event(line: str) -> None:
    import json
    from datetime import datetime, timezone

    try:
        event = json.loads(line)
    except ValueError:
        return
    kind = event.get("kind", "?")
    ts = event.get("ts")
    when = ""
    if isinstance(ts, (int, float)):
        when = datetime.fromtimestamp(ts, timezone.utc).strftime("%H:%M:%S") + "  "
    extra = "  ".join(f"{k}={v}" for k, v in event.items() if k not in ("ts", "kind"))
    print(f"{when}{_paint(kind, *_state_style(kind))}  {extra}".rstrip())


def _cmd_execution_watch(args: argparse.Namespace) -> int:
    import time

    store_root = _store_root()
    if store_root is None:
        return 4
    store = async_jobs.JobStore(store_root)
    if not store.exists(args.job_id):
        print(f"gmlc: no such job {args.job_id!r}", file=sys.stderr)
        return 4
    events_path = store.events_path(args.job_id)
    seen = 0

    def drain() -> int:
        nonlocal seen
        if not events_path.exists():
            return seen
        lines = events_path.read_text(encoding="utf-8").splitlines()
        for line in lines[seen:]:
            _print_event(line)
        seen = len(lines)
        return seen

    while True:
        drain()
        _, state = _job_state(store, args.job_id)
        if state in (async_jobs.SUCCEEDED, async_jobs.FAILED):
            time.sleep(0.05)  # let the terminal event (written just after status) land
            drain()
            return 0
        if state == async_jobs.INTERRUPTED:
            drain()
            print(
                f"gmlc: job {args.job_id} was interrupted — the worker vanished before finishing",
                file=sys.stderr,
            )
            return 1
        time.sleep(0.2)


def _materialize_output_files(execution: MlExecution, blob_store, output_dir: Path) -> int:
    """Write a stored execution's OUTPUT_FILE artifacts into ``output_dir`` (hydrating
    content from the blob store). Returns the number of files written."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base = output_dir.resolve()
    count = 0
    for artifact in execution.artifacts:
        if artifact.artifact_type is not ArtifactType.OUTPUT_FILE or artifact.name is None:
            continue
        target = (output_dir / Path(artifact.name)).resolve()
        if base != target and base not in target.parents:
            raise ValueError(f"refusing to write outside output dir: {artifact.name!r}")
        content = artifact.content
        if content is None:
            content = blob_store.get(artifact.blob_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content or b"")
        count += 1
    return count


def _cmd_execution_materialize(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    store = async_jobs.JobStore(store_root)
    if not store.exists(args.job_id):
        print(f"gmlc: no such job {args.job_id!r}", file=sys.stderr)
        return 4
    status, state = _job_state(store, args.job_id)
    status = status or {}
    if state != async_jobs.SUCCEEDED:
        print(f"gmlc: job {args.job_id} is {state}; nothing to materialize", file=sys.stderr)
        return 4
    key = status.get("execution_key")
    if not key:
        print(f"gmlc: job {args.job_id} has no stored result", file=sys.stderr)
        return 4
    token = _resolve_token(args)
    output_dir = Path(args.output_dir)
    try:
        wired = build_use_cases(store_root, encryption_token=token)
        execution = wired.repository.find_current(key)
        if execution is None:
            print(f"gmlc: job {args.job_id} has no stored result", file=sys.stderr)
            return 4
        count = _materialize_output_files(execution, wired.blob_store, output_dir)
    except (EncryptionTokenRequired, WrongEncryptionToken) as exc:
        print(f"gmlc: {exc} (set --token or GMLCACHE_TOKEN)", file=sys.stderr)
        return 4
    print(f"wrote {count} file(s) to {output_dir}")
    return 0


def _cmd_execution(args: argparse.Namespace) -> int:
    print(
        "usage: gmlcache execution status <id> | result <id> | watch <id> | "
        "materialize <id> --output-dir <path> | list",
        file=sys.stderr,
    )
    return 2


def _cmd_check(args: argparse.Namespace) -> int:
    import json

    from generic_ml_cache_core.application.domain.model.probe.probe_status import ProbeStatus
    from generic_ml_cache_core.application.port.inbound.probe_command import ProbeCommand

    context = _read_text_arg(args.context, args.context_file, "context")
    prompt = _read_text_arg(args.prompt, args.prompt_file, "prompt")
    if not prompt:
        raise SystemExit("error: a non-empty --prompt or --prompt-file is required")
    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    command = ProbeCommand(
        client=args.client,
        model=args.model,
        effort=args.effort,
        context=context,
        prompt=prompt,
        input_file_paths=_resolve_input_file_paths(args.input_file),
        allow_paths=_resolve_allow_paths(args.allow_path),
        scan_trust=bool(settings["trust_scan"][0]),
        client_args=list(getattr(args, "client_arg", None) or []),
        grants=list(getattr(args, "grant", None) or []),
    )
    report = build_use_cases(store_root).probe.execute(command)
    execution = report.execution
    usage = execution.token_usage if execution is not None else None
    file_count = (
        len([a for a in execution.artifacts if a.artifact_type is ArtifactType.OUTPUT_FILE])
        if execution is not None
        else 0
    )

    if args.json:
        payload = {
            "status": report.status.value,
            "cached": report.status is ProbeStatus.HIT,
            "client": args.client,
            "model": args.model,
            "effort": args.effort,
            "key": report.execution_key,
        }
        if execution is not None:
            payload["files"] = file_count
            payload["usage"] = usage.to_dict() if usage is not None else None
        print(json.dumps(payload, indent=2))
        return 0

    status_styles = {
        ProbeStatus.HIT: (_GREEN, _BOLD),
        ProbeStatus.MISS: (_AMBER, _BOLD),
        ProbeStatus.NON_CACHEABLE: (_GREY,),
    }
    print(f"status  : {_paint(report.status.value, *status_styles.get(report.status, ()))}")
    print(f"client  : {args.client}")
    print(f"model   : {args.model}")
    print(f"effort  : {args.effort}")
    print(f"key     : {report.execution_key}")
    if report.status is ProbeStatus.HIT and execution is not None:
        print(f"files   : {file_count}")
        if usage is None:
            print("usage   : (none captured)")
        else:
            print(f"usage   : {_usage_summary(usage)}")
    elif report.status is ProbeStatus.NON_CACHEABLE:
        print("note    : declares allow-path folders the cache cannot fingerprint, so this")
        print("          call always runs fresh and is never cached.")
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    matches = build_use_cases(store_root).repository.find_current_by_key_prefix(args.execution)
    if not matches:
        print(f"gmlc: no current execution matches key {args.execution!r}", file=sys.stderr)
        return 4
    if len(matches) > 1:
        print(
            f"gmlc: key {args.execution!r} is ambiguous — matches {len(matches)} executions:",
            file=sys.stderr,
        )
        for ambiguous in matches:
            print(f"  {ambiguous.call_identity.generate_key()}", file=sys.stderr)
        return 4

    execution = matches[0]
    print(f"key    : {execution.call_identity.generate_key()}")
    print(f"kind   : {execution.execution_kind.value}")
    print(f"state  : {execution.execution_state.value}")
    output_files = [a for a in execution.artifacts if a.artifact_type is ArtifactType.OUTPUT_FILE]
    print(f"files  : {len(output_files)}")
    for artifact in output_files:
        print(f"         - {artifact.name} ({artifact.encoding}, {artifact.size_bytes} bytes)")
    input_parts = [a for a in execution.artifacts if a.artifact_type in INPUT_ARTIFACT_TYPES]
    if input_parts:
        print(f"input  : stored ({len(input_parts)} part(s))")
        for artifact in input_parts:
            label = artifact.artifact_type.value.replace("input_", "")
            print(f"         - {label} ({artifact.encoding}, {artifact.size_bytes} bytes)")
    else:
        print("input  : not stored")
    usage = execution.token_usage
    if usage is None:
        print("usage  : (none captured)")
    else:
        print(f"usage  : {_usage_summary(usage)}")
        if usage.cost_usd is not None:
            print(f"         cost ~ ${usage.cost_usd:.4f} (client estimate, not authoritative)")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from generic_ml_cache_core.adapter.out.client.discover import probe_all

    try:
        file_cfg = config.load()
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    statuses = probe_all(timeout=args.timeout, executables=file_cfg.executables)

    if args.json:
        import json

        print(json.dumps([asdict(s) for s in statuses], indent=2))
        return 0

    if not statuses:
        print("no client adapters are registered")
        return 0
    print("configured clients (advisory — discovery never chooses or gates a run):")
    for s in statuses:
        if s.present:
            print(f"  {s.name:<8} present  {(s.version or 'version unknown'):<28}  {s.executable}")
        else:
            print(f"  {s.name:<8} missing  {s.detail or ''}")
    return 0


def _cmd_models(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from generic_ml_cache_core.adapter.out.api.api_discover import list_api_models
    from generic_ml_cache_core.adapter.out.client.discover import list_models, list_models_all
    from generic_ml_cache_core.common.errors import UnknownClient

    try:
        file_cfg = config.load()
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    if args.client:
        executable = config.executable_for(file_cfg, args.client, flag=args.executable)
        try:
            listings = [list_models(args.client, executable=executable, timeout=args.timeout)]
        except UnknownClient:
            # Not a CLI client — try the API provider registry (gemini, anthropic, …).
            listings = [list_api_models(args.client)]
    else:
        listings = list_models_all(timeout=args.timeout, executables=file_cfg.executables)

    if args.json:
        import json

        # Always valid JSON on every path (absent / unsupported / listed), so a
        # caller can parse the output unconditionally.
        print(json.dumps([asdict(m) for m in listings], indent=2))
        return 0

    for ml in listings:
        if not ml.present:
            print(f"  {ml.name:<8} absent   {ml.reason or ''}")
            continue
        if not ml.supported:
            print(f"  {ml.name:<8} —        {ml.reason or 'model listing not supported'}")
            continue
        if ml.models is None:
            print(f"  {ml.name:<8} —        {ml.reason or 'could not list models'}")
            continue
        print(f"  {ml.name:<8} {len(ml.models)} model(s) (advisory; relayed from the client):")
        for m in ml.models:
            marker = " (default)" if m.default else (" (current)" if m.current else "")
            print(f"      {m.id:<34} {m.name}{marker}")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    try:
        file_cfg = config.load()
        settings = config.resolve_settings(file_cfg)  # no run flags: env > file > default
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    path = config.resolve_config_path()
    loaded = file_cfg.source is not None
    encryption = FilesystemEncryptionManifestStore(Path(str(settings["store"][0]))).state().value

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "config_file": str(path),
                    "loaded": loaded,
                    "encryption": encryption,
                    "settings": {k: {"value": v[0], "source": v[1]} for k, v in settings.items()},
                    "executables": dict(file_cfg.executables),
                },
                indent=2,
            )
        )
        return 0

    print(f"config file : {path}  ({'loaded' if loaded else 'not present'})")
    print(f"encryption  : {encryption}")
    print("effective settings (no run flags applied):")
    for key in ("mode", "persist", "store", "timeout", "trust_scan", "max_size"):
        value, source = settings[key]
        shown = "none" if value is None else value
        if isinstance(shown, bool):
            shown = "true" if shown else "false"
        print(f"  {key:<10} {str(shown):<14} (from {source})")
    if file_cfg.executables:
        print("executables (from config; --executable still overrides per call):")
        for client, exe in file_cfg.executables.items():
            print(f"  {client:<8} {exe}")
    else:
        print("executables : none configured (clients resolved on PATH)")
    return 0


def _cmd_daemon(args: argparse.Namespace) -> int:
    print("usage: gmlcache daemon {start,stop,status}", file=sys.stderr)
    return 1


def _cmd_daemon_start(args: argparse.Namespace) -> int:
    try:
        from generic_ml_cache_daemon.app import create_app  # noqa: PLC0415
    except ImportError:
        print(
            "error: generic-ml-cache-daemon is not installed. "
            "Install it with: pip install generic-ml-cache-daemon",
            file=sys.stderr,
        )
        return 1
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:
        print("error: uvicorn is not installed (install generic-ml-cache-daemon)", file=sys.stderr)
        return 1

    store_root = _store_root()
    if store_root is None:
        return 4

    session_id: Optional[str] = getattr(args, "session", None) or None
    enable_metrics: bool = getattr(args, "metrics", False)
    host: str = args.host
    port: int = args.port

    application = create_app(store_root, session_id=session_id, enable_metrics=enable_metrics)
    uvicorn.run(application, host=host, port=port)
    return 0


def _cmd_daemon_status(args: argparse.Namespace) -> int:
    import json as _json  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    host: str = args.host
    port: int = args.port
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
            data = _json.loads(resp.read())
            status = data.get("status", "unknown")
    except urllib.error.URLError:
        status = "not running"
        if not getattr(args, "json", False):
            print(f"daemon: {status}")
            return 1

    if getattr(args, "json", False):
        import json as _json2  # noqa: PLC0415

        print(_json2.dumps({"status": status, "host": host, "port": port}))
    else:
        print(f"daemon: {status} (http://{host}:{port})")
    return 0 if status == "ok" else 1


def _cmd_daemon_stop(args: argparse.Namespace) -> int:
    import signal  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    host: str = args.host
    port: int = args.port
    health_url = f"http://{host}:{port}/health"
    try:
        urllib.request.urlopen(health_url, timeout=3)  # noqa: S310
    except urllib.error.URLError:
        print("daemon: not running", file=sys.stderr)
        return 1

    store_root = _store_root()
    pid_path = (store_root / ".daemon.pid") if store_root else None
    if pid_path is None or not pid_path.exists():
        print("daemon: running but no PID file found — send SIGTERM manually", file=sys.stderr)
        return 1

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        pid_path.unlink(missing_ok=True)
        print(f"daemon: sent SIGTERM to PID {pid}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"daemon: failed to stop — {exc}", file=sys.stderr)
        return 1


def _cmd_init(args: argparse.Namespace) -> int:
    try:
        path, created = config.write_default_config()
    except OSError as exc:
        print(f"gmlc: could not create config: {exc}", file=sys.stderr)
        return 4
    if created:
        print(f"created config: {path}")
    else:
        print(f"config already present: {path}  (left unchanged)")
    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    value, source = settings["store"]
    print(f"store: {value}  (from {source})")
    return 0


def _token_str(count: "int | None") -> str:
    """A token count for display: the number, or ``?`` when unknown (None)."""
    return "?" if count is None else str(count)


def _usage_summary(usage) -> str:
    """One-line token summary; unknown counts show as ``?`` (never 0)."""
    return (
        f"input={_token_str(usage.input_tokens)} "
        f"output={_token_str(usage.output_tokens)} "
        f"cache-read={_token_str(usage.cache_read_tokens)} "
        f"cache-write={_token_str(usage.cache_write_tokens)} "
        f"reasoning={_token_str(usage.reasoning_tokens)}"
    )


def _cmd_stats(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    max_size_bytes = settings["max_size"][0]
    wired = build_use_cases(Path(str(settings["store"][0])))
    summaries = wired.repository.current_execution_summaries()
    store_bytes = wired.repository.total_stored_bytes()
    access = wired.metrics.event_counts()
    by_client_model: Dict[tuple, int] = {}
    for summary in summaries:
        by_client_model[(summary.client, summary.model)] = (
            by_client_model.get((summary.client, summary.model), 0) + 1
        )

    if args.json:
        print(
            json.dumps(
                {
                    "executions": len(summaries),
                    "store_bytes": store_bytes,
                    "max_size_bytes": max_size_bytes,
                    "by_client_model": [
                        {"client": client, "model": model, "executions": count}
                        for (client, model), count in sorted(by_client_model.items())
                    ],
                    "access_events": access,
                },
                indent=2,
            )
        )
        return 0

    print(f"executions : {_paint(str(len(summaries)), _TEAL, _BOLD)}")
    if max_size_bytes:
        pct = int(store_bytes * 100 / max_size_bytes) if max_size_bytes > 0 else 0
        size_color = _AMBER if store_bytes >= max_size_bytes * 0.8 else _TEAL
        size_text = f"{_paint(_format_bytes(store_bytes), size_color)} / {_format_bytes(max_size_bytes)} ({pct}%)"
    else:
        size_text = _paint(_format_bytes(store_bytes), _TEAL)
    print(f"store size : {size_text}")
    if by_client_model:
        print("by client / model:")
        for (client, model), count in sorted(by_client_model.items()):
            print(f"  {client:<8} {model:<26} {count:>5}")
    if access:
        event_styles = {
            "hit": (_GREEN,),
            "miss": (_AMBER,),
            "record": (_TEAL,),
            "would_hit": (_GREEN,),
            "would_miss": (_AMBER,),
        }
        parts = ", ".join(
            f"{_paint(event, *event_styles.get(event, ()))}={count}"
            for event, count in sorted(access.items())
        )
        print(f"access     : {parts}")
    else:
        print("access     : (no events recorded yet)")
    return 0


_PURGE_ALL_PHRASE = "purge all"
_HARD_DELETE_ALL_PHRASE = "hard delete all"


def _cmd_purge(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    key = getattr(args, "key", None)
    tag = getattr(args, "tag", None)
    session = getattr(args, "session", None)
    session_tag = getattr(args, "session_tag", None)
    purge_all = getattr(args, "all", False)
    hard = getattr(args, "hard", False)
    confirm = getattr(args, "confirm", None)

    selectors = [bool(key), bool(tag), bool(session), bool(session_tag), bool(purge_all)]
    if sum(selectors) == 0:
        print(
            "gmlc: provide a target: <key>, --tag, --session, --session-tag, or --all",
            file=sys.stderr,
        )
        return 1
    if sum(selectors) > 1:
        print(
            "gmlc: only one of <key>, --tag, --session, --session-tag, --all may be given",
            file=sys.stderr,
        )
        return 1

    if purge_all:
        required = _HARD_DELETE_ALL_PHRASE if hard else _PURGE_ALL_PHRASE
        if confirm != required:
            verb = "hard-delete" if hard else "purge"
            print(
                f"gmlc: this will {verb} every execution in the store. "
                f'Add --confirm "{required}" to proceed.',
                file=sys.stderr,
            )
            return 4

    wired = build_use_cases(Path(str(settings["store"][0])))
    svc = wired.purge

    if key:
        report = svc.hard_delete_one(key) if hard else svc.purge_one(key)
    elif tag:
        report = svc.hard_delete_by_tag(tag) if hard else svc.purge_by_tag(tag)
    elif session:
        report = svc.hard_delete_by_session(session) if hard else svc.purge_by_session(session)
    elif session_tag:
        report = (
            svc.hard_delete_by_session_tag(session_tag)
            if hard
            else svc.purge_by_session_tag(session_tag)
        )
    else:
        report = svc.hard_delete_all() if hard else svc.purge_all()

    if args.json:
        print(
            json.dumps(
                {
                    "executions_removed": report.executions_removed,
                    "bytes_freed": report.bytes_freed,
                    "blobs_removed": report.blobs_removed,
                },
                indent=2,
            )
        )
        return 0

    if report.executions_removed == 0:
        print("nothing to purge")
        return 0

    verb = "deleted" if hard else "purged"
    print(
        f"{verb:<8} : "
        f"{_paint(str(report.executions_removed), _TEAL, _BOLD)} execution(s), "
        f"{_paint(_format_bytes(report.bytes_freed), _TEAL)} freed, "
        f"{report.blobs_removed} blob(s) removed"
    )
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    wired = build_use_cases(Path(str(settings["store"][0])))
    hit_counts = wired.metrics.hit_counts_by_key()
    entries = [
        {
            "client": summary.client,
            "model": summary.model,
            "kind": summary.kind,
            "key": summary.execution_key,
            "hits": hit_counts.get(summary.execution_key, 0),
            "tags": wired.repository.tags_for(summary.execution_key),
        }
        for summary in wired.repository.current_execution_summaries()
        if (not args.client or summary.client == args.client)
        and (not args.model or summary.model == args.model)
    ]
    wanted_tags = set(getattr(args, "tag", None) or [])
    if wanted_tags:
        entries = [entry for entry in entries if wanted_tags & set(entry["tags"])]
    excluded_tags = set(getattr(args, "exclude_tag", None) or [])
    if excluded_tags:
        entries = [entry for entry in entries if not excluded_tags & set(entry["tags"])]
    wanted_session_tags = list(getattr(args, "session_tag", None) or [])
    if wanted_session_tags:
        allowed_keys: set = set()
        for session_tag in wanted_session_tags:
            for session_id in wired.metrics.session_ids_for_tag(session_tag):
                allowed_keys.update(wired.metrics.execution_keys_for_session(session_id))
        entries = [entry for entry in entries if entry["key"] in allowed_keys]

    if args.json:
        print(json.dumps({"executions": entries}, indent=2))
        return 0

    if not entries:
        print("no current executions")
        return 0

    print(f"executions : {_paint(str(len(entries)), _TEAL, _BOLD)}")
    for entry in sorted(entries, key=lambda item: (item["client"], item["model"], item["key"])):
        hits = entry["hits"]
        hits_text = _paint(str(hits), _GREEN) if hits else _paint(str(hits), _GREY)
        line = (
            f"  {entry['client']:<8} {entry['model']:<20} {entry['kind']:<18} "
            f"{_paint(entry['key'][:12], _GREY)}  hits:{hits_text}"
        )
        if entry["tags"]:
            line += "  tags:" + _paint(",".join(entry["tags"]), _TEAL)
        print(line)
    return 0


def _cmd_tags(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    wired = build_use_cases(Path(str(settings["store"][0])))
    counts: dict = {}
    for summary in wired.repository.current_execution_summaries():
        for tag in wired.repository.tags_for(summary.execution_key):
            counts[tag] = counts.get(tag, 0) + 1

    tags = [{"tag": tag, "count": counts[tag]} for tag in sorted(counts)]

    if args.json:
        print(json.dumps({"tags": tags}, indent=2))
        return 0

    if not tags:
        print("no tags")
        return 0

    print(f"tags : {_paint(str(len(tags)), _TEAL, _BOLD)}")
    for entry in tags:
        count_text = _paint("count:" + str(entry["count"]), _GREY)
        print(f"  {entry['tag']:<24} {count_text}")
    return 0


_INPUT_FIELD_BY_TYPE = {
    ArtifactType.INPUT_CONTEXT: "context",
    ArtifactType.INPUT_PROMPT: "prompt",
    ArtifactType.INPUT_SYSTEM: "system",
}


def _export_record(summary, execution, tags, blob_store) -> dict:
    """Assemble one raw corpus record: the stored input parts and the output,
    hydrated from the blob store. Curation is the user's (tags); this never
    judges quality."""
    import base64
    import json

    def text(artifact) -> str:
        return (blob_store.get(artifact.blob_key) or b"").decode("utf-8", "replace")

    input_obj: dict = {}
    stdout = ""
    files = []
    for artifact in execution.artifacts:
        field_name = _INPUT_FIELD_BY_TYPE.get(artifact.artifact_type)
        if field_name is not None:
            input_obj[field_name] = text(artifact)
        elif artifact.artifact_type is ArtifactType.INPUT_MESSAGES:
            input_obj["messages"] = json.loads(text(artifact))
        elif artifact.artifact_type is ArtifactType.INPUT_ARGS:
            input_obj["args"] = json.loads(text(artifact))
        elif artifact.artifact_type is ArtifactType.STDOUT:
            stdout = text(artifact)
        elif artifact.artifact_type is ArtifactType.OUTPUT_FILE:
            if artifact.encoding == "binary":
                raw = blob_store.get(artifact.blob_key) or b""
                files.append(
                    {"name": artifact.name, "content_base64": base64.b64encode(raw).decode("ascii")}
                )
            else:
                files.append({"name": artifact.name, "content": text(artifact)})

    output_obj: dict = {"stdout": stdout}
    if files:
        output_obj["files"] = files
    return {
        "key": summary.execution_key,
        "kind": summary.kind,
        "client": summary.client,
        "model": summary.model,
        "tags": tags,
        "input": input_obj,
        "output": output_obj,
    }


def _cmd_export(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    include = set(getattr(args, "tag", None) or [])
    exclude = set(getattr(args, "exclude_tag", None) or [])

    lines = []
    skipped_no_input = 0
    try:
        wired = build_use_cases(
            Path(str(settings["store"][0])), encryption_token=_resolve_token(args)
        )
        for summary in wired.repository.current_execution_summaries():
            tags = wired.repository.tags_for(summary.execution_key)
            if include and not include & set(tags):
                continue
            if exclude and exclude & set(tags):
                continue
            execution = wired.repository.find_current(summary.execution_key)
            # Only DATASET-depth entries carry the input side of the corpus.
            if execution is None or not execution.input_persisted:
                skipped_no_input += 1
                continue
            lines.append(json.dumps(_export_record(summary, execution, tags, wired.blob_store)))
    except (EncryptionTokenRequired, WrongEncryptionToken) as exc:
        print(f"gmlc: {exc} (set --token or GMLCACHE_TOKEN)", file=sys.stderr)
        return 4

    if args.output:
        Path(args.output).write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        destination = args.output
    else:
        for line in lines:
            print(line)
        destination = "stdout"

    # Summary on stderr so stdout stays a clean JSONL stream.
    note = f"exported {len(lines)} record(s) to {destination}"
    if skipped_no_input:
        entries = "entry" if skipped_no_input == 1 else "entries"
        note += f"; skipped {skipped_no_input} matching {entries} without stored input (not dataset depth)"
    print(note, file=sys.stderr)
    return 0


# -- encryption -------------------------------------------------------------


def _resolve_token(args: argparse.Namespace) -> Optional[str]:
    """The encryption token for this call: the --token flag, else GMLCACHE_TOKEN.
    A token is a secret, so it is never read from the config file."""
    flag = getattr(args, "token", None)
    return flag if flag else (os.environ.get("GMLCACHE_TOKEN") or None)


def _load_cipher():
    """Build the cipher, with a friendly error if the optional extra is missing."""
    try:
        from generic_ml_cache_core.adapter.out.crypto.aesgcm_cipher import AesGcmCipher
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SystemExit(
            "error: encryption needs an optional dependency — install with "
            '`pip install "generic-ml-cache-core[encryption]"`'
        ) from exc
    return AesGcmCipher()


def _store_encryptor(store_root: Path, cipher=None) -> StoreEncryptor:
    return StoreEncryptor(
        store_root,
        FilesystemEncryptionManifestStore(store_root),
        SqliteStoreLock(store_root),
        cipher,
    )


def _store_root() -> Optional[Path]:
    try:
        return Path(str(config.resolve_settings(config.load())["store"][0]))
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return None


def _cmd_encrypt(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    cipher = _load_cipher()
    token = cipher.generate_token()
    try:
        _store_encryptor(store_root, cipher).enable(token)
    except (EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("encryption enabled. Save this token — it is shown once and cannot be recovered:")
    print(f"\n    {token}\n")
    print("Pass it with --token or GMLCACHE_TOKEN to read or write this store.")
    return 0


def _cmd_decrypt(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    token = _resolve_token(args)
    if not token:
        print("gmlc: provide the token with --token or GMLCACHE_TOKEN", file=sys.stderr)
        return 4
    try:
        _store_encryptor(store_root, _load_cipher()).disable(token)
    except (WrongEncryptionToken, EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("encryption disabled. The store is now public; no token is needed.")
    return 0


def _cmd_rotate(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    old_token = _resolve_token(args)
    if not old_token:
        print("gmlc: provide the current token with --token or GMLCACHE_TOKEN", file=sys.stderr)
        return 4
    cipher = _load_cipher()
    new_token = cipher.generate_token()
    try:
        _store_encryptor(store_root, cipher).rotate(old_token, new_token)
    except (WrongEncryptionToken, EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("token rotated. Save the new token — it is shown once:")
    print(f"\n    {new_token}\n")
    return 0


def _cmd_invalidate(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    if not args.yes:
        print(
            "gmlc: this permanently wipes the cache (crypto-shred) and cannot be undone. "
            "Re-run with --yes to confirm.",
            file=sys.stderr,
        )
        return 4
    try:
        _store_encryptor(store_root).invalidate()  # no token needed
    except StoreLocked as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("store invalidated: the cache was wiped and is now empty and public.")
    return 0


# -- sessions ---------------------------------------------------------------


def _resolve_session(args: argparse.Namespace) -> Optional[str]:
    """The session id for this run: the --session flag, else GMLCACHE_SESSION. A session
    groups a workflow's calls; it is journal metadata, never part of the cache key."""
    flag = getattr(args, "session", None)
    return flag if flag else (os.environ.get("GMLCACHE_SESSION") or None)


def _parse_spec_args(args: argparse.Namespace) -> "Optional[SessionSpec]":
    """Return a SessionSpec from --client/--model/--effort, or None if all are absent.
    Raises ValueError on a partial spec (some but not all flags supplied).
    """
    client = getattr(args, "client", None)
    model = getattr(args, "model", None)
    effort = getattr(args, "effort", None)
    provided = [x is not None for x in (client, model, effort)]
    if not any(provided):
        return None
    if not all(provided):
        raise ValueError("--client, --model, and --effort must all be supplied together")
    return SessionSpec(client=client, model=model, effort=effort)


def _cmd_session_start(args: argparse.Namespace) -> int:
    import secrets

    session_id = secrets.token_hex(8)
    # Print only the id, so it is scriptable: SESSION=$(gmlcache session start)
    print(session_id)
    tags = getattr(args, "tag", None) or []
    try:
        spec = _parse_spec_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if tags or spec:
        settings = config.resolve_settings(config.load())
        wired = build_use_cases(Path(str(settings["store"][0])))
        for tag in tags:
            wired.metrics.add_session_tag(session_id, tag)
        if spec is not None:
            wired.metrics.set_session_spec(session_id, spec)
    return 0


def _cmd_session_update(args: argparse.Namespace) -> int:
    try:
        spec = _parse_spec_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if spec is None:
        print(
            "error: --client, --model, and --effort are all required for session update",
            file=sys.stderr,
        )
        return 2
    store_root = _store_root()
    if store_root is None:
        return 4
    wired = build_use_cases(store_root)
    wired.metrics.set_session_spec(args.session_id, spec)
    if not args.json:
        print(f"spec  : {spec.client}/{spec.model}/{spec.effort!r}")
    else:
        import json

        print(
            json.dumps(
                {
                    "session": args.session_id,
                    "spec": {
                        "client": spec.client,
                        "model": spec.model,
                        "effort": spec.effort,
                    },
                },
                indent=2,
            )
        )
    return 0


def _cmd_session_clear_spec(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    wired = build_use_cases(store_root)
    wired.metrics.clear_session_spec(args.session_id)
    if not args.json:
        print(f"spec cleared for session {args.session_id}")
    else:
        import json

        print(json.dumps({"session": args.session_id, "spec": None}, indent=2))
    return 0


_TOKEN_BLOCKS = " ▏▎▍▌▋▊▉█"


def _activity_bar(value: int, maxval: int, width: int = 10) -> str:
    if maxval <= 0:
        return " " * width
    filled = value / maxval * width
    full = int(filled)
    bar = "█" * full + (_TOKEN_BLOCKS[int((filled - full) * 8)] if full < width else "")
    return (bar + " " * width)[:width]


def _comma(n: int) -> str:
    return f"{n:,}"


def _render_session_report(report, tags: list = None) -> str:
    lines = [f"session     : {report.session_id}"]
    if tags:
        lines.append(f"tags        : {', '.join(sorted(tags))}")
    if report.span_start:
        span = (
            report.span_start
            if report.day_count == 1
            else f"{report.span_start} → {report.span_end}"
        )
        plural = "" if report.day_count == 1 else "s"
        lines.append(f"span        : {span}  ({report.day_count} day{plural})")
    lines.append(
        f"invocations : {report.invocations}   "
        f"executions : {report.executions}   hits : {report.hits}"
    )
    if report.unknown_usage:
        lines.append(f"unknown     : {report.unknown_usage} execution(s) reported no usage")
    if report.by_model:
        lines.append("")
        lines.append("by provider / model:")
        for m in report.by_model:
            lines.append(
                f"  {m.client + ' / ' + m.model:<16} spent {_comma(m.spent_tokens):>9} tok"
                f" (in {_comma(m.spent_input):>8} · out {_comma(m.spent_output):>7})"
                f"   saved {_comma(m.saved_tokens):>9} tok   {m.executions} exec · {m.hits} hit"
            )
    if report.by_day:
        lines.append("")
        lines.append("by day (activity):")
        maxinv = max(d.invocations for d in report.by_day)
        for d in report.by_day:
            lines.append(
                f"  {d.day}  {_activity_bar(d.invocations, maxinv)}  {d.invocations:>3} calls"
                f"   ({d.executions} exec · {d.hits} hit)"
            )
    return "\n".join(lines)


def _session_report_json(report, tags: list) -> dict:
    return {
        "session": report.session_id,
        "tags": tags,
        "invocations": report.invocations,
        "executions": report.executions,
        "hits": report.hits,
        "unknown_usage": report.unknown_usage,
        "span": {"start": report.span_start, "end": report.span_end, "days": report.day_count},
        "by_model": [
            {
                "client": m.client,
                "model": m.model,
                "spent_input": m.spent_input,
                "spent_output": m.spent_output,
                "spent_tokens": m.spent_tokens,
                "saved_tokens": m.saved_tokens,
                "executions": m.executions,
                "hits": m.hits,
            }
            for m in report.by_model
        ],
        "by_day": [
            {
                "day": d.day,
                "invocations": d.invocations,
                "executions": d.executions,
                "hits": d.hits,
            }
            for d in report.by_day
        ],
    }


def _cmd_session_report(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    session_id = getattr(args, "session_id", None)
    tag = getattr(args, "tag", None)
    if not session_id and not tag:
        print("gmlc: provide a session id or --tag <tag>", file=sys.stderr)
        return 1
    wired = build_use_cases(store_root)

    if tag:
        return _cmd_session_report_by_tag(wired, tag, args.json)

    events = wired.metrics.session_events(session_id)
    tags = wired.metrics.session_tags(session_id)
    # Join each event's execution to its token usage (the current execution per key).
    usage_by_key = {}
    for key in {e.execution_key for e in events if e.execution_key}:
        execution = wired.repository.find_current(key)
        if execution is not None:
            usage_by_key[key] = execution.token_usage
    report = build_session_report(session_id, events, usage_by_key)

    if args.json:
        import json

        print(json.dumps(_session_report_json(report, tags), indent=2))
        return 0
    if report.invocations == 0 and not tags:
        print(f"no events recorded for session {session_id!r}")
        return 0
    print(_render_session_report(report, tags))
    return 0


def _cmd_session_report_by_tag(wired, tag: str, as_json: bool) -> int:
    session_ids = wired.metrics.session_ids_for_tag(tag)
    if not session_ids:
        print(f"no sessions tagged {tag!r}")
        return 0
    # Collect events from all matching sessions; build one merged report.
    all_events = []
    for session_id in session_ids:
        all_events.extend(wired.metrics.session_events(session_id))
    usage_by_key = {}
    for key in {e.execution_key for e in all_events if e.execution_key}:
        execution = wired.repository.find_current(key)
        if execution is not None:
            usage_by_key[key] = execution.token_usage
    report = build_session_report(tag, all_events, usage_by_key)

    if as_json:
        import json

        payload = _session_report_json(report, [tag])
        payload["tag"] = tag
        payload["session_count"] = len(session_ids)
        del payload["session"]
        print(json.dumps(payload, indent=2))
        return 0
    lines = [f"tag         : {tag}", f"sessions    : {len(session_ids)}"]
    print("\n".join(lines))
    print(_render_session_report(report))
    return 0


def _cmd_session_tag(args: argparse.Namespace) -> int:
    if not args.add and not args.remove:
        print("error: supply at least one --add or --remove flag", file=sys.stderr)
        return 2
    store_root = _store_root()
    if store_root is None:
        return 4
    wired = build_use_cases(store_root)
    for tag in args.add:
        wired.metrics.add_session_tag(args.session_id, tag)
    for tag in args.remove:
        wired.metrics.remove_session_tag(args.session_id, tag)
    if not args.json:
        tags = wired.metrics.session_tags(args.session_id)
        print(f"tags : {', '.join(sorted(tags))}")
    else:
        import json

        tags = wired.metrics.session_tags(args.session_id)
        print(json.dumps({"session": args.session_id, "tags": tags}, indent=2))
    return 0


def _cmd_session(args: argparse.Namespace) -> int:
    print(
        "usage: gmlcache session start | tag | update | clear-spec | report",
        file=sys.stderr,
    )
    return 2


def _use_color() -> bool:
    """Colour only when writing to a real terminal and NO_COLOR is unset, so piped
    or redirected output never carries escape codes (the conventional contract)."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


# ANSI palette (256-colour). One place for the escape codes, shared by the banner
# and the status/stats colouring.
_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_TEAL = "\x1b[38;5;37m"  # accent / box rule
_TEAL_BRIGHT = "\x1b[38;5;43m"  # version
_GREEN = "\x1b[38;5;42m"  # a hit
_AMBER = "\x1b[38;5;214m"  # a miss
_GREY = "\x1b[38;5;245m"  # secondary / dim


def _paint(text: str, *codes: str) -> str:
    """Wrap ``text`` in ANSI codes when colour is enabled (a real TTY with NO_COLOR
    unset), else return it unchanged -- so piped output never carries escape codes.
    Only gmlcache's own UI is ever painted; a client's answer is printed verbatim."""
    if not codes or not _use_color():
        return text
    return "".join(codes) + text + _RESET


def _format_bytes(n: int) -> str:
    """Human-readable byte count using 1024-based units."""
    for unit, threshold in (("GB", 1 << 30), ("MB", 1 << 20), ("KB", 1 << 10)):
        if n >= threshold:
            return f"{n / threshold:.1f} {unit}"
    return f"{n} B"


def render_banner(color: bool = False) -> str:
    """The boxed gmlcache banner: the cache mark (four hollow bars; the top one is
    the accent 'hit') beside the title, version, and tagline. Width is derived from
    the content so everything stays aligned. ``color`` adds ANSI; off yields plain."""
    title = "gmlcache"
    ver = __version__
    tag = "record · replay · check · sessions · encryption"

    # The mark: four hollow bars -- thin walls (▏ ▕) around a double-line body (═),
    # widths echoing the logo. The first bar is the accent ("hit"); the rest are dim.
    bars = ["▏" + "═" * n + "▕" for n in (11, 7, 10, 5)]
    bar_w = max(len(b) for b in bars)

    if color:
        rule, name, vers, sub, off = _TEAL, _BOLD, _TEAL_BRIGHT, _GREY, _RESET
        bar_colors = [_GREEN, _GREY, _GREY, _GREY]
    else:
        rule = name = vers = sub = off = ""
        bar_colors = ["", "", "", ""]

    left_pad, gap = "  ", "  "
    texts = ["", tag, "", ""]  # the tagline sits on the second bar row

    body_w = max(len(left_pad) + bar_w + len(gap) + len(t) for t in texts)
    left_top = f"─ {title} "
    right_top = f" {ver} ─"
    inner = max(len(left_top) + 6 + len(right_top), body_w + 1)
    top_dashes = inner - len(left_top) - len(right_top)

    top = (
        f"{rule}┌─ {off}{name}{title}{off}"
        f"{rule} {'─' * top_dashes} {off}{vers}{ver}{off}{rule} ─┐{off}"
    )
    rows = []
    for bar, bar_color, text in zip(bars, bar_colors, texts):
        bar_cell = f"{bar_color}{bar}{off}" + " " * (bar_w - len(bar))
        used = len(left_pad) + bar_w + len(gap) + len(text)
        rows.append(
            f"{rule}│{off}{left_pad}{bar_cell}{gap}{sub}{text}{off}"
            f"{' ' * (inner - used)}{rule}│{off}"
        )
    bot = f"{rule}└{'─' * inner}┘{off}"
    return "\n".join([top, *rows, bot])


class _BannerParser(argparse.ArgumentParser):
    """An ArgumentParser whose full help is fronted by the banner, so the banner
    shows on ``-h`` and on a bare invocation (but not on terse usage/error lines)."""

    def format_help(self) -> str:
        return render_banner(_use_color()) + "\n\n" + super().format_help()


def _add_shared_run_options(parser: argparse.ArgumentParser) -> None:
    """Add the run-resolution options shared by `run` and `alias` (mode, persistence,
    record policy, the executable seam, encryption token, session, timeout). Both
    commands resolve a cached call the same way, so they share this surface verbatim."""
    parser.add_argument(
        "--mode",
        choices=[m.value for m in CacheMode],
        default=None,
        help="resolution mode (default: cache, or config/env)",
    )
    parser.add_argument(
        "--persist",
        choices=[d.value for d in PersistenceDepth],
        default=None,
        help=(
            "how much to keep: meter (usage only, never replays), cache (+output, "
            "the default), or dataset (+input) (default: cache, or config/env)"
        ),
    )
    parser.add_argument("--offline", action="store_true", help="shortcut for --mode offline")
    parser.add_argument("--force", action="store_true", help="shortcut for --mode refresh")
    parser.add_argument(
        "--record-on-error",
        action="store_true",
        help="also cache a call that fails (non-zero exit); default is to store only successes",
    )
    parser.add_argument("--executable", help="override the client executable (the seam)")
    parser.add_argument(
        "--token", help="encryption token for an encrypted store (or set GMLCACHE_TOKEN)"
    )
    parser.add_argument(
        "--session", help="group this run under a session id (or set GMLCACHE_SESSION)"
    )
    parser.add_argument(
        "--timeout", type=float, default=None, help="seconds before the real call is killed"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _BannerParser(
        prog="gmlcache",
        description="Content-addressed cache/proxy for agentic CLI calls.",
    )
    parser.add_argument("--version", action="version", version=f"gmlcache {__version__}")
    # metavar curates the usage/positional display (and hides internal commands like
    # __worker, which argparse's help=SUPPRESS does not reliably hide for subparsers).
    sub = parser.add_subparsers(dest="command", required=False, metavar="<command>")

    run = sub.add_parser("run", help="resolve a request (record on miss, replay on hit)")
    run.add_argument("--client", required=True, choices=registered_names() + registered_api_names())
    run.add_argument("--model", required=True)
    run.add_argument(
        "--effort",
        default="",
        help=(
            "reasoning effort (optional); omit to use the client's own default. "
            "For Cursor, leave this off when the model id already encodes effort."
        ),
    )
    run.add_argument("--prompt")
    run.add_argument("--prompt-file")
    run.add_argument("--context")
    run.add_argument("--context-file")
    run.add_argument("--system-prompt")
    run.add_argument("--system-prompt-file")
    run.add_argument(
        "--input-file",
        action="append",
        dest="input_file",
        metavar="PATH",
        help=(
            "a specific file the client will read in place; its content is "
            "fingerprinted into the cache key and the client is granted read "
            "access to it. Repeatable, any file type. The key watches content, "
            "not the name."
        ),
    )
    run.add_argument(
        "--allow-path",
        action="append",
        dest="allow_path",
        metavar="PATH",
        help=(
            "a folder the client may scan/read whose contents the cache cannot "
            "fingerprint. Declaring any allow-path makes the call run fresh and "
            "store nothing (non-cacheable). The client is granted read access to "
            "it via the prime directive (and --add-dir on Claude). Repeatable."
        ),
    )
    run.add_argument(
        "--client-arg",
        action="append",
        dest="client_arg",
        metavar="ARG",
        help=(
            "an extra argument appended verbatim to the client launch -- an escape "
            "hatch for client features the cache does not model. Part of the key "
            "(different args = different execution); only its fingerprint is stored, "
            "never the raw value. Repeatable; order is significant. Pass a "
            "dash-leading value with the =form: --client-arg=--flag."
        ),
    )
    run.add_argument(
        "--grant",
        action="append",
        dest="grant",
        choices=GRANT_CHOICES,
        help=_GRANT_HELP,
    )
    run.add_argument(
        "--tag",
        action="append",
        dest="tag",
        metavar="TAG",
        help=(
            "label this execution with a tag for later grouping/queries (repeatable; "
            "metadata only -- never part of the cache key). A relabel on a hit accumulates."
        ),
    )
    run.add_argument(
        "--json",
        action="store_true",
        help=(
            "emit a machine-readable JSON envelope (status, exit, files, normalized "
            "usage, stdout) instead of the raw answer -- for a parent process such "
            "as the workflow engine reading usage. Files are still written to the cwd."
        ),
    )
    _add_shared_run_options(run)
    run.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print cache diagnostics to stderr (breaks exact fidelity)",
    )
    run.add_argument(
        "--stream",
        nargs="?",
        const="./gmlc-stream.jsonl",
        default=None,
        metavar="PATH",
        help=(
            "write a live NDJSON progress stream as the call runs (run.start, the client's "
            "thinking/tool events, run.end) -- display-only, never changes what is recorded. "
            "Give a path, or pass --stream alone to write ./gmlc-stream.jsonl"
        ),
    )
    run.add_argument(
        "--detach",
        action="store_true",
        help=(
            "submit the run as a detached background job: print an execution id and return "
            "immediately; the work continues, queryable with `gmlcache execution ...`"
        ),
    )
    run.set_defaults(func=_cmd_run)

    aliasp = sub.add_parser(
        "alias",
        help=(
            "thin native-client wrapper: cache a raw native invocation -- everything "
            "after the client is passed to it verbatim and is the cache identity"
        ),
        description=(
            "Run a client through the cache as a thin wrapper. gmlcache's own options "
            "(below) come BEFORE the client; everything after the client is forwarded to "
            "it verbatim and keyed (by fingerprint) as the cache identity. No options are "
            "modelled or auto-completed. A replay reproduces the native call's stdout, "
            "stderr and exit; generated files are written by the live call only (no capture). "
            "Drop-in: alias claude='gmlcache alias claude'."
        ),
    )
    _add_shared_run_options(aliasp)
    aliasp.add_argument("client", choices=registered_names(), help="the native client to wrap")
    aliasp.add_argument(
        "native_args",
        nargs=argparse.REMAINDER,
        metavar="-- NATIVE_ARGS",
        help="the native client arguments, forwarded verbatim (this is the cache identity)",
    )
    aliasp.set_defaults(func=_cmd_alias)

    # Internal: no help= so it never appears as a help row; metavar hides it from the list.
    worker = sub.add_parser("__worker")
    worker.add_argument("store_root")
    worker.add_argument("job_id")
    worker.set_defaults(func=_cmd_worker)

    inspect = sub.add_parser("inspect", help="show a stored execution by its (short) key")
    inspect.add_argument("execution", help="an execution key, or a short prefix as shown by `list`")
    inspect.set_defaults(func=_cmd_inspect)

    check = sub.add_parser(
        "check",
        help="probe whether a call is already cached (read-only; launches and records nothing)",
    )
    check.add_argument("--client", required=True, choices=registered_names())
    check.add_argument("--model", required=True)
    check.add_argument(
        "--effort",
        default="",
        help="reasoning effort (optional); must match the run you would make",
    )
    check.add_argument("--prompt")
    check.add_argument("--prompt-file")
    check.add_argument("--context")
    check.add_argument("--context-file")
    check.add_argument(
        "--input-file",
        action="append",
        dest="input_file",
        metavar="PATH",
        help="an input file whose content is fingerprinted into the key (repeatable)",
    )
    check.add_argument(
        "--allow-path",
        action="append",
        dest="allow_path",
        metavar="PATH",
        help="a scan folder; declaring any makes the call non-cacheable (repeatable)",
    )
    check.add_argument(
        "--client-arg",
        action="append",
        dest="client_arg",
        metavar="ARG",
        help="extra arg keyed into the call, to probe a passthrough launch (repeatable)",
    )
    check.add_argument(
        "--grant",
        action="append",
        dest="grant",
        choices=GRANT_CHOICES,
        help="open a capability (net/read/write/shell/web-search), keyed into the call, to probe a granted launch (repeatable)",
    )
    check.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    check.set_defaults(func=_cmd_check)

    doctor = sub.add_parser(
        "doctor",
        help="report which configured clients are present + their versions (advisory)",
    )
    doctor.add_argument(
        "--timeout", type=float, default=10.0, help="seconds before a version check is killed"
    )
    doctor.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    doctor.set_defaults(func=_cmd_doctor)

    models = sub.add_parser(
        "models",
        help="list the models a client reports it can use (advisory; relayed from the client)",
    )
    models.add_argument(
        "client",
        nargs="?",
        help="client or API provider name (e.g. claude, gemini); omit to query every registered client",
    )
    models.add_argument("--executable", help="override the client executable (the seam)")
    models.add_argument(
        "--timeout", type=float, default=30.0, help="seconds before the listing call is killed"
    )
    models.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    models.set_defaults(func=_cmd_models)

    status = sub.add_parser(
        "status",
        help="show the resolved configuration (which file loaded, effective settings)",
    )
    status.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    status.set_defaults(func=_cmd_status)

    stats = sub.add_parser(
        "stats",
        help="show how many executions are stored, their total size split by client/model, "
        "and access counts",
    )
    stats.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    stats.set_defaults(func=_cmd_stats)

    purgep = sub.add_parser(
        "purge",
        help="free stored blobs (soft purge) or erase all records (--hard)",
    )
    purgep.add_argument("key", nargs="?", help="execution key to purge")
    purgep.add_argument("--tag", help="purge all executions carrying this tag")
    purgep.add_argument("--session", help="purge all executions from this session")
    purgep.add_argument(
        "--session-tag",
        dest="session_tag",
        help="purge all executions from sessions carrying this tag",
    )
    purgep.add_argument("--all", action="store_true", help="purge every execution in the store")
    purgep.add_argument(
        "--hard",
        action="store_true",
        help="hard-delete: also remove DB records and access history "
        "(default: soft purge keeps statistics)",
    )
    purgep.add_argument(
        "--confirm",
        help='confirmation phrase required for --all (soft: "purge all"; hard: "hard delete all")',
    )
    purgep.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    purgep.set_defaults(func=_cmd_purge)

    listp = sub.add_parser(
        "list", help="list stored executions, grouped by client/model (read-only)"
    )
    listp.add_argument("--client", help="only executions recorded for this client")
    listp.add_argument("--model", help="only executions recorded for this model")
    listp.add_argument(
        "--tag",
        action="append",
        dest="tag",
        metavar="TAG",
        help="only executions carrying any of these tags (repeatable; match-any)",
    )
    listp.add_argument(
        "--exclude-tag",
        action="append",
        dest="exclude_tag",
        metavar="TAG",
        help="drop executions carrying any of these tags (repeatable; match-any)",
    )
    listp.add_argument(
        "--session-tag",
        action="append",
        dest="session_tag",
        metavar="TAG",
        help="only executions from sessions carrying this tag (repeatable; match-any)",
    )
    listp.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    listp.set_defaults(func=_cmd_list)

    tagsp = sub.add_parser(
        "tags",
        help="list the distinct tags in use across current executions, with counts (read-only)",
    )
    tagsp.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    tagsp.set_defaults(func=_cmd_tags)

    exportp = sub.add_parser(
        "export",
        help="export the (input, output) dataset corpus as JSONL (read-only). Only entries "
        "stored at --persist dataset carry an input; others are skipped.",
    )
    exportp.add_argument(
        "--tag",
        action="append",
        dest="tag",
        metavar="TAG",
        help="only entries carrying any of these tags (repeatable; match-any)",
    )
    exportp.add_argument(
        "--exclude-tag",
        action="append",
        dest="exclude_tag",
        metavar="TAG",
        help="drop entries carrying any of these tags (repeatable; match-any)",
    )
    exportp.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write JSONL to FILE instead of stdout (a per-record summary still goes to stderr)",
    )
    exportp.add_argument(
        "--token", help="encryption token if the store is encrypted (or set GMLCACHE_TOKEN)"
    )
    exportp.set_defaults(func=_cmd_export)

    encryptp = sub.add_parser(
        "encrypt", help="enable at-rest encryption of the store (generates and shows a token)"
    )
    encryptp.set_defaults(func=_cmd_encrypt)

    decryptp = sub.add_parser(
        "decrypt", help="disable encryption (decrypts the store back to plaintext; needs the token)"
    )
    decryptp.add_argument("--token", help="the encryption token (or set GMLCACHE_TOKEN)")
    decryptp.set_defaults(func=_cmd_decrypt)

    rotatep = sub.add_parser(
        "rotate", help="rotate the encryption token (needs the current token; shows the new one)"
    )
    rotatep.add_argument("--token", help="the current encryption token (or set GMLCACHE_TOKEN)")
    rotatep.set_defaults(func=_cmd_rotate)

    invalidatep = sub.add_parser(
        "invalidate",
        help="wipe the cache (crypto-shred) — the escape when the token is lost. Needs --yes.",
    )
    invalidatep.add_argument("--yes", action="store_true", help="confirm the irreversible wipe")
    invalidatep.set_defaults(func=_cmd_invalidate)

    session = sub.add_parser("session", help="group a workflow's runs under a session id")
    session_sub = session.add_subparsers(dest="session_command")
    session_start = session_sub.add_parser("start", help="generate a new session id and print it")
    session_start.add_argument(
        "--tag",
        action="append",
        metavar="TAG",
        help="attach a tag to the session (repeatable)",
    )
    session_start.add_argument("--client", metavar="CLIENT", help="adapter for the session spec")
    session_start.add_argument("--model", metavar="MODEL", help="model for the session spec")
    session_start.add_argument(
        "--effort",
        metavar="EFFORT",
        help="effort for the session spec (empty string for Cursor)",
    )
    session_start.set_defaults(func=_cmd_session_start)
    session_update = session_sub.add_parser(
        "update", help="replace the execution spec on an existing session"
    )
    session_update.add_argument("session_id", help="the session id to update")
    session_update.add_argument(
        "--client", required=True, metavar="CLIENT", help="adapter for the new spec"
    )
    session_update.add_argument(
        "--model", required=True, metavar="MODEL", help="model for the new spec"
    )
    session_update.add_argument(
        "--effort",
        required=True,
        metavar="EFFORT",
        help="effort for the new spec (empty string for Cursor)",
    )
    session_update.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    session_update.set_defaults(func=_cmd_session_update)
    session_clear_spec = session_sub.add_parser(
        "clear-spec", help="remove the execution spec from an existing session"
    )
    session_clear_spec.add_argument("session_id", help="the session id to clear the spec from")
    session_clear_spec.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    session_clear_spec.set_defaults(func=_cmd_session_clear_spec)
    session_tag_cmd = session_sub.add_parser(
        "tag", help="add or remove tags on an existing session"
    )
    session_tag_cmd.add_argument("session_id", help="the session id to tag")
    session_tag_cmd.add_argument(
        "--add",
        action="append",
        default=[],
        metavar="TAG",
        help="tag to attach (repeatable)",
    )
    session_tag_cmd.add_argument(
        "--remove",
        action="append",
        default=[],
        metavar="TAG",
        help="tag to detach (repeatable)",
    )
    session_tag_cmd.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    session_tag_cmd.set_defaults(func=_cmd_session_tag)
    session_report = session_sub.add_parser("report", help="summarise a session's activity")
    session_report.add_argument(
        "session_id",
        nargs="?",
        help="the session id to report on (omit when using --tag)",
    )
    session_report.add_argument(
        "--tag",
        metavar="TAG",
        help="aggregate all sessions sharing this tag",
    )
    session_report.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    session_report.set_defaults(func=_cmd_session_report)
    session.set_defaults(func=_cmd_session)

    execution = sub.add_parser("execution", help="inspect detached (--detach) execution jobs")
    execution_sub = execution.add_subparsers(dest="execution_command")
    exec_status = execution_sub.add_parser("status", help="show a detached job's state")
    exec_status.add_argument("job_id", help="the execution id printed by `run --detach`")
    exec_status.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    exec_status.set_defaults(func=_cmd_execution_status)
    exec_result = execution_sub.add_parser("result", help="print a finished job's output")
    exec_result.add_argument("job_id", help="the execution id")
    exec_result.add_argument(
        "--token", help="encryption token if the store is encrypted (or set GMLCACHE_TOKEN)"
    )
    exec_result.set_defaults(func=_cmd_execution_result)
    exec_watch = execution_sub.add_parser(
        "watch", help="replay a job's event log, following it live if still running"
    )
    exec_watch.add_argument("job_id", help="the execution id")
    exec_watch.set_defaults(func=_cmd_execution_watch)
    exec_mat = execution_sub.add_parser(
        "materialize", help="write a finished job's generated files to a directory"
    )
    exec_mat.add_argument("job_id", help="the execution id")
    exec_mat.add_argument(
        "--output-dir", required=True, help="directory to write the generated files into"
    )
    exec_mat.add_argument(
        "--token", help="encryption token if the store is encrypted (or set GMLCACHE_TOKEN)"
    )
    exec_mat.set_defaults(func=_cmd_execution_materialize)
    exec_list = execution_sub.add_parser("list", help="list detached jobs and their states")
    exec_list.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    exec_list.set_defaults(func=_cmd_execution_list)
    execution.set_defaults(func=_cmd_execution)

    init = sub.add_parser(
        "init",
        help="create the config file in the default location (if absent), then show the store",
    )
    init.set_defaults(func=_cmd_init)

    daemon = sub.add_parser("daemon", help="manage the generic-ml-cache HTTP daemon")
    daemon_sub = daemon.add_subparsers(dest="daemon_command")

    _daemon_host_port = {"host": "127.0.0.1", "port": 8765}

    daemon_start = daemon_sub.add_parser("start", help="start the HTTP daemon (foreground)")
    daemon_start.add_argument("--host", default=_daemon_host_port["host"], metavar="HOST")
    daemon_start.add_argument("--port", type=int, default=_daemon_host_port["port"], metavar="PORT")
    daemon_start.add_argument("--session", metavar="SESSION_ID", help="bind daemon to a session")
    daemon_start.add_argument("--metrics", action="store_true", help="enable Prometheus /metrics")
    daemon_start.set_defaults(func=_cmd_daemon_start)

    daemon_status = daemon_sub.add_parser("status", help="check if the daemon is running")
    daemon_status.add_argument("--host", default=_daemon_host_port["host"], metavar="HOST")
    daemon_status.add_argument(
        "--port", type=int, default=_daemon_host_port["port"], metavar="PORT"
    )
    daemon_status.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    daemon_status.set_defaults(func=_cmd_daemon_status)

    daemon_stop = daemon_sub.add_parser("stop", help="send SIGTERM to a running daemon")
    daemon_stop.add_argument("--host", default=_daemon_host_port["host"], metavar="HOST")
    daemon_stop.add_argument("--port", type=int, default=_daemon_host_port["port"], metavar="PORT")
    daemon_stop.set_defaults(func=_cmd_daemon_stop)

    daemon.set_defaults(func=_cmd_daemon)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    if argcomplete is not None:
        # A no-op unless the shell is requesting completions (it sets _ARGCOMPLETE);
        # in that case it emits candidates and exits, so it never affects normal runs.
        argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
