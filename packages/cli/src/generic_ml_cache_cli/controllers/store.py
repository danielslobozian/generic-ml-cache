# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: store commands — check, inspect, stats, purge, list, tags, export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, TypedDict

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    INPUT_ARTIFACT_TYPES,
    Artifact,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.probe.probe_report import ProbeReport
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_command import (
    ReadArtifactBlobCommand,
)
from generic_ml_cache_core.application.port.inbound.artifact_content.read_artifact_blob_use_case import (
    ReadArtifactBlobUseCase,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_current_execution_command import (
    FindCurrentExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.execution_query.find_executions_by_key_prefix_command import (
    FindExecutionsByKeyPrefixCommand,
)
from generic_ml_cache_core.application.port.inbound.execution_query.tags_for_execution_command import (
    TagsForExecutionCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_all_command import PurgeAllCommand
from generic_ml_cache_core.application.port.inbound.purge.purge_by_key_command import (
    PurgeByKeyCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_command import (
    PurgeBySessionCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_session_tag_command import (
    PurgeBySessionTagCommand,
)
from generic_ml_cache_core.application.port.inbound.purge.purge_by_tag_command import (
    PurgeByTagCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.execution_keys_for_session_command import (
    ExecutionKeysForSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.sessions_for_tag_command import (
    SessionsForTagCommand,
)
from generic_ml_cache_core.application.wiring.application_api import ApplicationApi
from generic_ml_cache_core.common.errors import (
    ConfigError,
    EncryptionTokenRequired,
    WrongEncryptionToken,
)

from generic_ml_cache_cli import config
from generic_ml_cache_cli._compose import build_use_cases
from generic_ml_cache_cli.composition import (
    make_diag,
    read_text_arg,
    resolve_allow_paths,
    resolve_input_file_paths,
    resolve_token,
)
from generic_ml_cache_cli.presenters.shared import (
    AMBER,
    BOLD,
    GREEN,
    GREY,
    TEAL,
    format_bytes,
    paint,
    usage_summary,
)

_PURGE_ALL_PHRASE = "purge all"
_HARD_DELETE_ALL_PHRASE = "hard delete all"

_INPUT_FIELD_BY_TYPE = {
    ArtifactType.INPUT_CONTEXT: "context",
    ArtifactType.INPUT_PROMPT: "prompt",
    ArtifactType.INPUT_SYSTEM: "system",
}


def _print_check_result(
    report: ProbeReport,
    args: argparse.Namespace,
    execution: MlExecution | None,
    usage: TokenUsage | None,
    file_count: int,
) -> None:
    from generic_ml_cache_core.application.domain.model.probe.probe_status import ProbeStatus

    status_styles: dict[ProbeStatus, tuple[str, ...]] = {
        ProbeStatus.HIT: (GREEN, BOLD),
        ProbeStatus.MISS: (AMBER, BOLD),
        ProbeStatus.NON_CACHEABLE: (GREY,),
    }
    print(f"status  : {paint(report.status.value, *status_styles.get(report.status, ()))}")
    print(f"client  : {args.client}")
    print(f"model   : {args.model}")
    print(f"effort  : {args.effort}")
    print(f"key     : {report.execution_key}")
    if report.status is ProbeStatus.HIT and execution is not None:
        print(f"files   : {file_count}")
        if usage is None:
            print("usage   : (none captured)")
        else:
            print(f"usage   : {usage_summary(usage)}")
    elif report.status is ProbeStatus.NON_CACHEABLE:
        print("note    : declares allow-path folders the cache cannot fingerprint, so this")
        print("          call always runs fresh and is never cached.")


def cmd_check(args: argparse.Namespace) -> int:
    import json

    from generic_ml_cache_core.application.domain.model.probe.probe_status import ProbeStatus
    from generic_ml_cache_core.application.port.inbound.probe.probe_command import ProbeCommand

    context = read_text_arg(args.context, args.context_file, "context")
    prompt = read_text_arg(args.prompt, args.prompt_file, "prompt")
    system_prompt = (
        read_text_arg(args.system_prompt, args.system_prompt_file, "system-prompt") or None
    )
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
        user_system_prompt=system_prompt,
        input_file_paths=tuple(resolve_input_file_paths(args.input_file)),
        allow_paths=tuple(resolve_allow_paths(args.allow_path)),
        scan_trust=bool(settings["trust_scan"][0]),
        client_args=tuple(getattr(args, "client_arg", None) or []),
        grants=tuple(getattr(args, "grant", None) or []),
    )
    report = build_use_cases(store_root, diag=make_diag(args)).probe.execute(command)
    execution = report.execution
    usage = execution.token_usage if execution is not None else None
    file_count = (
        len([a for a in execution.artifacts if a.artifact_type is ArtifactType.OUTPUT_FILE])
        if execution is not None
        else 0
    )

    if args.json:
        payload: dict[str, object] = {
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

    _print_check_result(report, args, execution, usage, file_count)
    return 0


def _artifact_status_suffix(artifact: Artifact) -> str:
    """A ``[pending]``/``[failed]`` marker for a non-STORED artifact (C-4); empty
    for the normal STORED case, so a healthy execution reads unchanged."""
    return "" if artifact.is_stored else f" [{artifact.status.value}]"


def _print_inspect_artifacts(execution: MlExecution) -> None:
    output_files = [a for a in execution.artifacts if a.artifact_type is ArtifactType.OUTPUT_FILE]
    print(f"files  : {len(output_files)}")
    for artifact in output_files:
        suffix = _artifact_status_suffix(artifact)
        print(
            f"         - {artifact.name} ({artifact.encoding}, {artifact.size_bytes} bytes){suffix}"
        )
    input_parts = [a for a in execution.artifacts if a.artifact_type in INPUT_ARTIFACT_TYPES]
    if input_parts:
        print(f"input  : stored ({len(input_parts)} part(s))")
        for artifact in input_parts:
            label = artifact.artifact_type.value.replace("input_", "")
            suffix = _artifact_status_suffix(artifact)
            print(f"         - {label} ({artifact.encoding}, {artifact.size_bytes} bytes){suffix}")
    else:
        print("input  : not stored")
    if execution.has_failed_persistence:
        print("persist: INCOMPLETE — some artifacts failed to store; run `gmlcache repair`")


def cmd_inspect(args: argparse.Namespace) -> int:
    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    matches = build_use_cases(
        store_root, diag=make_diag(args)
    ).find_executions_by_key_prefix.find_by_key_prefix(
        FindExecutionsByKeyPrefixCommand(args.execution)
    )
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
    _print_inspect_artifacts(execution)
    usage = execution.token_usage
    if usage is None:
        print("usage  : (none captured)")
    else:
        print(f"usage  : {usage_summary(usage)}")
        if usage.cost_usd is not None:
            print(f"         cost ~ ${usage.cost_usd:.4f} (client estimate, not authoritative)")
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    """Reconcile runs left non-servable by an interrupted/failed blob write against
    what is actually in the blob store (C-4). Never re-runs the client."""
    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(store_root, diag=make_diag(args))
    report = wired.repair_store.repair()
    total = report.runs_recovered + report.runs_unrecoverable
    if total == 0:
        print("store repair: nothing to reconcile — all runs are fully persisted")
        return 0
    print(f"store repair: {total} run(s) had incomplete persistence")
    print(f"  recovered     : {report.runs_recovered} (blob present — now servable again)")
    print(f"  unrecoverable : {report.runs_unrecoverable} (blob missing — re-run with --refresh)")
    print(f"  blobs reconciled: {report.blobs_reconciled}, still missing: {report.blobs_missing}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    max_size_bytes = config.resolved_max_size(settings)
    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(store_root, diag=make_diag(args))
    summaries = wired.list_execution_summaries.list_summaries()
    store_bytes = wired.total_stored_bytes.total_stored_bytes()
    access = wired.event_counts.event_counts()
    by_client_model: dict[tuple[str, str], int] = {}
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

    print(f"executions : {paint(str(len(summaries)), TEAL, BOLD)}")
    if max_size_bytes:
        pct = int(store_bytes * 100 / max_size_bytes) if max_size_bytes > 0 else 0
        size_color = AMBER if store_bytes >= max_size_bytes * 0.8 else TEAL
        size_text = f"{paint(format_bytes(store_bytes), size_color)} / {format_bytes(max_size_bytes)} ({pct}%)"
    else:
        size_text = paint(format_bytes(store_bytes), TEAL)
    print(f"store size : {size_text}")
    if by_client_model:
        print("by client / model:")
        for (client, model), count in sorted(by_client_model.items()):
            print(f"  {client:<8} {model:<26} {count:>5}")
    if access:
        event_styles: dict[str, tuple[str, ...]] = {
            "hit": (GREEN,),
            "miss": (AMBER,),
            "record": (TEAL,),
            "would_hit": (GREEN,),
            "would_miss": (AMBER,),
        }
        parts = ", ".join(
            f"{paint(event, *event_styles.get(event, ()))}={count}"
            for event, count in sorted(access.items())
        )
        print(f"access     : {parts}")
    else:
        print("access     : (no events recorded yet)")
    return 0


def _dispatch_purge(
    wired: ApplicationApi,
    key: str | None,
    tag: str | None,
    session: str | None,
    session_tag: str | None,
    hard: bool,
) -> Any:
    if key:
        return wired.purge_by_key.purge_by_key(PurgeByKeyCommand(key, hard=hard))
    if tag:
        return wired.purge_by_tag.purge_by_tag(PurgeByTagCommand(tag, hard=hard))
    if session:
        return wired.purge_by_session.purge_by_session(PurgeBySessionCommand(session, hard=hard))
    if session_tag:
        return wired.purge_by_session_tag.purge_by_session_tag(
            PurgeBySessionTagCommand(session_tag, hard=hard)
        )
    return wired.purge_all.purge_all(PurgeAllCommand(hard=hard))


def cmd_purge(args: argparse.Namespace) -> int:
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

    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(store_root, diag=make_diag(args))
    report = _dispatch_purge(wired, key, tag, session, session_tag, hard)

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
        f"{paint(str(report.executions_removed), TEAL, BOLD)} execution(s), "
        f"{paint(format_bytes(report.bytes_freed), TEAL)} freed, "
        f"{report.blobs_removed} blob(s) removed"
    )
    return 0


def _keys_for_session_tags(
    wired: ApplicationApi,
    wanted_session_tags: list[str],
) -> set[str]:
    allowed: set[str] = set()
    for session_tag in wanted_session_tags:
        for session_id in wired.sessions_for_tag.sessions_for_tag(
            SessionsForTagCommand(session_tag)
        ):
            allowed.update(
                wired.execution_keys_for_session.execution_keys_for_session(
                    ExecutionKeysForSessionCommand(session_id)
                )
            )
    return allowed


class _ListedExecution(TypedDict):
    """One row of `gmlcache list`: an execution summary plus its hits and tags."""

    client: str
    model: str
    kind: str
    key: str
    hits: int
    tags: list[str]


def _print_list_text(entries: list[_ListedExecution]) -> None:
    if not entries:
        print("no current executions")
        return
    print(f"executions : {paint(str(len(entries)), TEAL, BOLD)}")
    for entry in sorted(entries, key=lambda item: (item["client"], item["model"], item["key"])):
        hits = entry["hits"]
        hits_text = paint(str(hits), GREEN) if hits else paint(str(hits), GREY)
        line = (
            f"  {entry['client']:<8} {entry['model']:<20} {entry['kind']:<18} "
            f"{paint(entry['key'][:12], GREY)}  hits:{hits_text}"
        )
        if entry["tags"]:
            line += "  tags:" + paint(",".join(entry["tags"]), TEAL)
        print(line)


def cmd_list(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(store_root, diag=make_diag(args))
    hit_counts = wired.hit_counts_by_key.hit_counts_by_key()
    entries: list[_ListedExecution] = [
        {
            "client": summary.client,
            "model": summary.model,
            "kind": summary.kind,
            "key": summary.execution_key,
            "hits": hit_counts.get(summary.execution_key, 0),
            "tags": wired.tags_for_execution.tags_for(
                TagsForExecutionCommand(summary.execution_key)
            ),
        }
        for summary in wired.list_execution_summaries.list_summaries()
        if (not args.client or summary.client == args.client)
        and (not args.model or summary.model == args.model)
    ]
    wanted_tags: set[str] = set(getattr(args, "tag", None) or [])
    if wanted_tags:
        entries = [entry for entry in entries if wanted_tags & set(entry["tags"])]
    excluded_tags: set[str] = set(getattr(args, "exclude_tag", None) or [])
    if excluded_tags:
        entries = [entry for entry in entries if not excluded_tags & set(entry["tags"])]
    wanted_session_tags: list[str] = list(getattr(args, "session_tag", None) or [])
    if wanted_session_tags:
        allowed_keys = _keys_for_session_tags(wired, wanted_session_tags)
        entries = [entry for entry in entries if entry["key"] in allowed_keys]

    if args.json:
        print(json.dumps({"executions": entries}, indent=2))
        return 0

    _print_list_text(entries)
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(store_root, diag=make_diag(args))
    counts: dict[str, int] = {}
    for summary in wired.list_execution_summaries.list_summaries():
        for tag in wired.tags_for_execution.tags_for(
            TagsForExecutionCommand(summary.execution_key)
        ):
            counts[tag] = counts.get(tag, 0) + 1

    tags = [{"tag": tag, "count": counts[tag]} for tag in sorted(counts)]

    if args.json:
        print(json.dumps({"tags": tags}, indent=2))
        return 0

    if not tags:
        print("no tags")
        return 0

    print(f"tags : {paint(str(len(tags)), TEAL, BOLD)}")
    for entry in tags:
        count_text = paint("count:" + str(entry["count"]), GREY)
        print(f"  {entry['tag']:<24} {count_text}")
    return 0


def _export_record(
    summary: Any,  # an ExecutionSummary from the outbound repository port; typed after decision B-1
    execution: MlExecution,
    tags: list[str],
    artifacts: ReadArtifactBlobUseCase,
) -> dict[str, object]:
    """Assemble one raw corpus record: the stored input parts and the output,
    hydrated from the blob store. Curation is the user's (tags); this never
    judges quality."""
    import base64
    import json

    def text(artifact: Artifact) -> str:
        return (artifacts.read_blob(ReadArtifactBlobCommand(artifact.blob_key)) or b"").decode(
            "utf-8", "replace"
        )

    input_obj: dict[str, object] = {}
    stdout = ""
    files: list[dict[str, object]] = []
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
                raw = artifacts.read_blob(ReadArtifactBlobCommand(artifact.blob_key)) or b""
                files.append(
                    {"name": artifact.name, "content_base64": base64.b64encode(raw).decode("ascii")}
                )
            else:
                files.append({"name": artifact.name, "content": text(artifact)})

    output_obj: dict[str, object] = {"stdout": stdout}
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


def _collect_export_lines(
    wired: ApplicationApi,
    include: set[str],
    exclude: set[str],
) -> tuple[list[str], int]:
    import json

    lines: list[str] = []
    skipped_no_input = 0
    for summary in wired.list_execution_summaries.list_summaries():
        tags = wired.tags_for_execution.tags_for(TagsForExecutionCommand(summary.execution_key))
        if include and not include & set(tags):
            continue
        if exclude and exclude & set(tags):
            continue
        execution = wired.find_current_execution.find_current(
            FindCurrentExecutionCommand(summary.execution_key)
        )
        # Only DATASET-depth entries carry the input side of the corpus.
        if execution is None or not execution.input_persisted:
            skipped_no_input += 1
            continue
        lines.append(json.dumps(_export_record(summary, execution, tags, wired.read_artifact_blob)))
    return lines, skipped_no_input


def cmd_export(args: argparse.Namespace) -> int:
    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    include: set[str] = set(getattr(args, "tag", None) or [])
    exclude: set[str] = set(getattr(args, "exclude_tag", None) or [])

    store_root = Path(str(settings["store"][0]))
    try:
        wired = build_use_cases(
            store_root,
            encryption_token=resolve_token(args),
            diag=make_diag(args),
        )
        lines, skipped_no_input = _collect_export_lines(wired, include, exclude)
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
