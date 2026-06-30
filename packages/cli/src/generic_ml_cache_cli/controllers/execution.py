# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: execution sub-commands — worker, status, result, list, watch, materialize."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.common.errors import (
    EncryptionTokenRequired,
    StoreLocked,
    WrongEncryptionToken,
)

from generic_ml_cache_cli import async_jobs
from generic_ml_cache_cli._compose import build_use_cases
from generic_ml_cache_cli.composition import (
    _db_conn_factory,
    _make_diag,
    _resolve_token,
    _store_root,
)
from generic_ml_cache_cli.controllers.run import (
    _command_from_spec,
    _spec_executable_override,
    _spec_whitelist,
)
from generic_ml_cache_cli.presenters.shared import (
    _AMBER,
    _GREEN,
    _GREY,
    _TEAL,
    _paint,
    _run_exit_code,
    _stored_artifact_text,
)


def _state_style(state: str):
    # Built at call time: the ANSI palette constants are defined in presenters/shared.
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
                    _db_conn_factory(store_root),
                    store_root,
                    _spec_executable_override(spec),
                    spec["timeout"],
                    encryption_token=token,
                    stream_path=str(events),  # client live events land in the job's log
                    client=spec["client"],
                    max_size=spec.get("max_size"),
                    whitelist=_spec_whitelist(spec),
                    diag=_make_diag(args),
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


def _print_job_status_text(job_id: str, status: dict, state: str) -> None:
    print(f"job        : {job_id}")
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
        print(f"result     : {status['execution_key'][:12]}  (gmlcache execution result {job_id})")
    if state == async_jobs.INTERRUPTED:
        print("note       : the worker vanished before finishing (lock released, no result)")
    elif state == async_jobs.FAILED and status.get("error"):
        print(f"error      : {status['error']}")


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
    _print_job_status_text(args.job_id, status, state)
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
        wired = build_use_cases(
            _db_conn_factory(store_root),
            store_root,
            encryption_token=token,
            diag=_make_diag(args),
        )
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


def _materialize_output_files(execution, blob_store, output_dir: Path) -> int:
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
        wired = build_use_cases(
            _db_conn_factory(store_root),
            store_root,
            encryption_token=token,
            diag=_make_diag(args),
        )
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


def _cmd_execution(_args: argparse.Namespace) -> int:
    print(
        "usage: gmlcache execution status <id> | result <id> | watch <id> | "
        "materialize <id> --output-dir <path> | list",
        file=sys.stderr,
    )
    return 2
