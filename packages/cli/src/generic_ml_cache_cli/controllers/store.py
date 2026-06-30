# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: store commands — check, inspect, stats, purge, list, tags, export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    INPUT_ARTIFACT_TYPES,
    ArtifactType,
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
from generic_ml_cache_core.common.errors import (
    ConfigError,
    EncryptionTokenRequired,
    WrongEncryptionToken,
)

from generic_ml_cache_cli import config
from generic_ml_cache_cli._compose import build_use_cases
from generic_ml_cache_cli.composition import (
    _db_conn_factory,
    _make_diag,
    _read_text_arg,
    _resolve_allow_paths,
    _resolve_input_file_paths,
    _resolve_token,
)
from generic_ml_cache_cli.presenters.shared import (
    _AMBER,
    _BOLD,
    _GREEN,
    _GREY,
    _TEAL,
    _format_bytes,
    _paint,
    _usage_summary,
)

_PURGE_ALL_PHRASE = "purge all"
_HARD_DELETE_ALL_PHRASE = "hard delete all"

_INPUT_FIELD_BY_TYPE = {
    ArtifactType.INPUT_CONTEXT: "context",
    ArtifactType.INPUT_PROMPT: "prompt",
    ArtifactType.INPUT_SYSTEM: "system",
}


def _print_check_result(report, args, execution, usage, file_count) -> None:
    from generic_ml_cache_core.application.domain.model.probe.probe_status import ProbeStatus

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


def _cmd_check(args: argparse.Namespace) -> int:
    import json

    from generic_ml_cache_core.application.domain.model.probe.probe_status import ProbeStatus
    from generic_ml_cache_core.application.port.inbound.probe_command import ProbeCommand

    context = _read_text_arg(args.context, args.context_file, "context")
    prompt = _read_text_arg(args.prompt, args.prompt_file, "prompt")
    system_prompt = (
        _read_text_arg(args.system_prompt, args.system_prompt_file, "system-prompt") or None
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
        input_file_paths=_resolve_input_file_paths(args.input_file),
        allow_paths=_resolve_allow_paths(args.allow_path),
        scan_trust=bool(settings["trust_scan"][0]),
        client_args=list(getattr(args, "client_arg", None) or []),
        grants=list(getattr(args, "grant", None) or []),
    )
    report = build_use_cases(
        _db_conn_factory(store_root), store_root, diag=_make_diag(args)
    ).probe.execute(command)
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

    _print_check_result(report, args, execution, usage, file_count)
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    matches = build_use_cases(
        _db_conn_factory(store_root), store_root, diag=_make_diag(args)
    ).execution_query.find_by_key_prefix(FindExecutionsByKeyPrefixCommand(args.execution))
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


def _cmd_stats(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    max_size_bytes: int | None = (
        int(settings["max_size"][0])  # type: ignore[arg-type]
        if settings["max_size"][0] is not None
        else None
    )
    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))
    summaries = wired.execution_query.list_summaries()
    store_bytes = wired.execution_query.total_stored_bytes()
    access = wired.metrics.event_counts()
    by_client_model: dict[tuple, int] = {}
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


def _dispatch_purge(svc, key, tag, session, session_tag, hard):
    if key:
        return svc.hard_delete_one(key) if hard else svc.purge_one(key)
    if tag:
        return svc.hard_delete_by_tag(tag) if hard else svc.purge_by_tag(tag)
    if session:
        return svc.hard_delete_by_session(session) if hard else svc.purge_by_session(session)
    if session_tag:
        return (
            svc.hard_delete_by_session_tag(session_tag)
            if hard
            else svc.purge_by_session_tag(session_tag)
        )
    return svc.hard_delete_all() if hard else svc.purge_all()


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

    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))
    report = _dispatch_purge(wired.purge, key, tag, session, session_tag, hard)

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


def _keys_for_session_tags(wired, wanted_session_tags: list) -> set:
    allowed: set = set()
    for session_tag in wanted_session_tags:
        for session_id in wired.metrics.session_ids_for_tag(session_tag):
            allowed.update(wired.metrics.execution_keys_for_session(session_id))
    return allowed


def _print_list_text(entries) -> None:
    if not entries:
        print("no current executions")
        return
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


def _cmd_list(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))
    hit_counts = wired.metrics.hit_counts_by_key()
    entries = [
        {
            "client": summary.client,
            "model": summary.model,
            "kind": summary.kind,
            "key": summary.execution_key,
            "hits": hit_counts.get(summary.execution_key, 0),
            "tags": wired.execution_query.tags_for(TagsForExecutionCommand(summary.execution_key)),
        }
        for summary in wired.execution_query.list_summaries()
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
        allowed_keys = _keys_for_session_tags(wired, wanted_session_tags)
        entries = [entry for entry in entries if entry["key"] in allowed_keys]

    if args.json:
        print(json.dumps({"executions": entries}, indent=2))
        return 0

    _print_list_text(entries)
    return 0


def _cmd_tags(args: argparse.Namespace) -> int:
    import json

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))
    counts: dict = {}
    for summary in wired.execution_query.list_summaries():
        for tag in wired.execution_query.tags_for(TagsForExecutionCommand(summary.execution_key)):
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


def _collect_export_lines(wired, include, exclude) -> tuple:
    import json

    lines = []
    skipped_no_input = 0
    for summary in wired.execution_query.list_summaries():
        tags = wired.execution_query.tags_for(TagsForExecutionCommand(summary.execution_key))
        if include and not include & set(tags):
            continue
        if exclude and exclude & set(tags):
            continue
        execution = wired.execution_query.find_current(
            FindCurrentExecutionCommand(summary.execution_key)
        )
        # Only DATASET-depth entries carry the input side of the corpus.
        if execution is None or not execution.input_persisted:
            skipped_no_input += 1
            continue
        lines.append(json.dumps(_export_record(summary, execution, tags, wired.blob_store)))
    return lines, skipped_no_input


def _cmd_export(args: argparse.Namespace) -> int:
    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    include = set(getattr(args, "tag", None) or [])
    exclude = set(getattr(args, "exclude_tag", None) or [])

    store_root = Path(str(settings["store"][0]))
    try:
        wired = build_use_cases(
            _db_conn_factory(store_root),
            store_root,
            encryption_token=_resolve_token(args),
            diag=_make_diag(args),
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
