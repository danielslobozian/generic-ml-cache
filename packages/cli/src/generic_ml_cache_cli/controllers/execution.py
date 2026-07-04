# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: execution sub-commands — worker, status, result, list, watch, materialize."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_command import (
    ReadArtifactBlobCommand,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_current_execution_command import (
    FindCurrentExecutionCommand,
)
from generic_ml_cache_core.common.errors import (
    EncryptionTokenRequired,
    StoreLocked,
    WrongEncryptionToken,
)

from generic_ml_cache_cli import async_jobs
from generic_ml_cache_cli._compose import build_use_cases
from generic_ml_cache_cli.composition import (
    db_conn_factory,
    make_diag,
    resolve_token,
    store_root,
)
from generic_ml_cache_cli.controllers.run import (
    command_from_spec,
    spec_executable_override,
    spec_max_size,
    spec_timeout,
    spec_whitelist,
)
from generic_ml_cache_cli.presenters.shared import (
    AMBER,
    GREEN,
    GREY,
    TEAL,
    paint,
    run_exit_code,
    stored_artifact_text,
)


def _state_style(state: str) -> tuple[str, ...]:
    # Built at call time: the ANSI palette constants are defined in presenters/shared.
    return {
        async_jobs.RUNNING: (TEAL,),
        async_jobs.SUBMITTED: (GREY,),
        async_jobs.SUCCEEDED: (GREEN,),
        async_jobs.FAILED: (AMBER,),
        async_jobs.INTERRUPTED: (AMBER,),
    }.get(state, ())


def _job_state(store: async_jobs.JobStore, job_id: str) -> tuple[dict[str, object] | None, str]:
    """(status dict or None, derived state) for a job, applying the liveness probe."""
    status = store.read_status(job_id)
    held = async_jobs.job_lock_held(store.lock_path(job_id))
    return status, async_jobs.derived_state(status, held)


def cmd_worker(args: argparse.Namespace) -> int:
    """Hidden: the detached worker. Run the job's managed execution while holding its
    liveness lock, recording the outcome to status.json. Never writes to the cwd."""
    store_root_path = Path(args.store_root)
    store = async_jobs.JobStore(store_root_path)
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
                command = command_from_spec(spec)
                # On an encrypted store the token arrives via the environment (set by the
                # spawner), never from disk; a public store ignores it.
                token = os.environ.get("GMLCACHE_TOKEN") or None
                wired = build_use_cases(
                    db_conn_factory(store_root_path),
                    store_root_path,
                    spec_executable_override(spec),
                    spec_timeout(spec),
                    encryption_token=token,
                    stream_path=str(events),  # client live events land in the job's log
                    client=command.client,
                    max_size=spec_max_size(spec),
                    whitelist=spec_whitelist(spec),
                    diag=make_diag(args),
                )
                execution = wired.run_ml.execute(command)
            except Exception as exc:  # noqa: BLE001 — detached-worker boundary: any failure → job FAILED
                store.update_status(
                    job_id, state=async_jobs.FAILED, ended_at=async_jobs.now(), error=str(exc)
                )
                async_jobs.append_event(events, "failed", error=str(exc))
                return 1
            key = execution.call_identity.generate_key()
            exit_code = run_exit_code(execution)
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


def _print_job_status_text(job_id: str, status: dict[str, object], state: str) -> None:
    print(f"job        : {job_id}")
    print(f"state      : {paint(state, *_state_style(state))}")
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
            f"result     : {str(status['execution_key'])[:12]}"
            f"  (gmlcache execution result {job_id})"
        )
    if state == async_jobs.INTERRUPTED:
        print("note       : the worker vanished before finishing (lock released, no result)")
    elif state == async_jobs.FAILED and status.get("error"):
        print(f"error      : {status['error']}")


def cmd_execution_status(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    store = async_jobs.JobStore(store_root_path)
    if not store.exists(args.job_id):
        print(f"gmlc: no such job {args.job_id!r}", file=sys.stderr)
        return 4
    status, state = _job_state(store, args.job_id)
    status = status or {}
    if args.json:
        import json

        print(json.dumps({**status, "state": state}, indent=2))
        return 0
    _print_job_status_text(args.job_id, status, state)
    return 0


def cmd_execution_result(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    store = async_jobs.JobStore(store_root_path)
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
    if not isinstance(key, str) or not key:
        print(f"gmlc: job {args.job_id} has no stored result", file=sys.stderr)
        return 4
    token = resolve_token(args)
    try:
        wired = build_use_cases(
            db_conn_factory(store_root_path),
            store_root_path,
            encryption_token=token,
            diag=make_diag(args),
        )
        execution = wired.execution_query.find_current(FindCurrentExecutionCommand(key))
        if execution is None:
            print(
                f"gmlc: job {args.job_id} has no stored result (was the cache pruned?)",
                file=sys.stderr,
            )
            return 4
        out = stored_artifact_text(execution, wired.artifacts, ArtifactType.STDOUT)
        err = stored_artifact_text(execution, wired.artifacts, ArtifactType.STDERR)
    except (EncryptionTokenRequired, WrongEncryptionToken) as exc:
        print(f"gmlc: {exc} (set --token or GMLCACHE_TOKEN)", file=sys.stderr)
        return 4
    sys.stdout.write(out)
    sys.stdout.flush()
    sys.stderr.write(err)
    sys.stderr.flush()
    recorded_exit_code = status.get("exit_code")
    return recorded_exit_code if isinstance(recorded_exit_code, int) else 0


def cmd_execution_list(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    store = async_jobs.JobStore(store_root_path)
    rows: list[tuple[str, str, object, object, object]] = []
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
        painted = paint(f"{state:<11}", *_state_style(state))
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
    print(f"{when}{paint(kind, *_state_style(kind))}  {extra}".rstrip())


def cmd_execution_watch(args: argparse.Namespace) -> int:
    import time

    store_root_path = store_root()
    if store_root_path is None:
        return 4
    store = async_jobs.JobStore(store_root_path)
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


def _materialize_output_files(
    execution: MlExecution,
    artifacts: Any,  # the ArtifactContentService inbound surface; typed after decision B-1
    output_dir: Path,
) -> int:
    """Write a stored execution's OUTPUT_FILE artifacts into ``output_dir`` (hydrating
    content via the artifact-content port). Returns the number of files written."""
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
            content = artifacts.read_blob(ReadArtifactBlobCommand(artifact.blob_key))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content or b"")
        count += 1
    return count


def cmd_execution_materialize(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    store = async_jobs.JobStore(store_root_path)
    if not store.exists(args.job_id):
        print(f"gmlc: no such job {args.job_id!r}", file=sys.stderr)
        return 4
    status, state = _job_state(store, args.job_id)
    status = status or {}
    if state != async_jobs.SUCCEEDED:
        print(f"gmlc: job {args.job_id} is {state}; nothing to materialize", file=sys.stderr)
        return 4
    key = status.get("execution_key")
    if not isinstance(key, str) or not key:
        print(f"gmlc: job {args.job_id} has no stored result", file=sys.stderr)
        return 4
    token = resolve_token(args)
    output_dir = Path(args.output_dir)
    try:
        wired = build_use_cases(
            db_conn_factory(store_root_path),
            store_root_path,
            encryption_token=token,
            diag=make_diag(args),
        )
        execution = wired.execution_query.find_current(FindCurrentExecutionCommand(key))
        if execution is None:
            print(f"gmlc: job {args.job_id} has no stored result", file=sys.stderr)
            return 4
        count = _materialize_output_files(execution, wired.artifacts, output_dir)
    except (EncryptionTokenRequired, WrongEncryptionToken) as exc:
        print(f"gmlc: {exc} (set --token or GMLCACHE_TOKEN)", file=sys.stderr)
        return 4
    print(f"wrote {count} file(s) to {output_dir}")
    return 0


def cmd_execution(_args: argparse.Namespace) -> int:
    print(
        "usage: gmlcache execution status <id> | result <id> | watch <id> | "
        "materialize <id> --output-dir <path> | list",
        file=sys.stderr,
    )
    return 2
