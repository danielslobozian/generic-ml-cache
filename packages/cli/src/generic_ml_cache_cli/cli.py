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

from generic_ml_cache_core.adapter.inbound.composition import build_use_cases
from generic_ml_cache_core.adapter.out.crypto.filesystem_encryption_manifest_store import (
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_core.adapter.out.crypto.store_encryptor import StoreEncryptor
from generic_ml_cache_core.adapter.out.persistence.sqlite_store_lock import SqliteStoreLock
from generic_ml_cache_core.adapter.out.client.registry import registered_names
from generic_ml_cache_core.application.domain.model.execution.artifact import (
    INPUT_ARTIFACT_TYPES,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.inbound.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
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


def _print_run_json(execution: MlExecution, command: RunManagedLocalExecutionCommand) -> int:
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


def _cmd_run(args: argparse.Namespace) -> int:
    context = _read_text_arg(args.context, args.context_file, "context")
    prompt = _read_text_arg(args.prompt, args.prompt_file, "prompt")
    if not prompt:
        raise SystemExit("error: a non-empty --prompt or --prompt-file is required")
    system_prompt = (
        _read_text_arg(args.system_prompt, args.system_prompt_file, "system-prompt") or None
    )

    try:
        file_cfg = config.load()
        settings = config.resolve_settings(
            file_cfg, mode_flag=args.mode, persist_flag=args.persist, timeout_flag=args.timeout
        )
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store_root = Path(str(settings["store"][0]))
    timeout = settings["timeout"][0]
    trust_scan = bool(settings["trust_scan"][0])
    # --offline / --force are explicit flags and win over the resolved mode.
    if args.offline:
        cache_mode = CacheMode.OFFLINE
    elif args.force:
        cache_mode = CacheMode.REFRESH
    else:
        cache_mode = CacheMode(str(settings["mode"][0]))
    persistence_depth = PersistenceDepth(str(settings["persist"][0]))

    command = RunManagedLocalExecutionCommand(
        client=args.client,
        model=args.model,
        effort=args.effort,
        context=context,
        prompt=prompt,
        user_system_prompt=system_prompt,
        input_file_paths=_resolve_input_file_paths(args.input_file),
        allow_paths=_resolve_allow_paths(args.allow_path),
        scan_trust=trust_scan,
        client_args=list(getattr(args, "client_arg", None) or []),
        grants=list(getattr(args, "grant", None) or []),
        cache_mode=cache_mode,
        persistence_depth=persistence_depth,
        record_on_error=args.record_on_error,
        tags=list(getattr(args, "tag", None) or []),
        session_id=_resolve_session(args),
    )

    def executable_override(client: str):
        return config.executable_for(file_cfg, client, flag=args.executable)

    token = _resolve_token(args)
    try:
        wired = build_use_cases(store_root, executable_override, timeout, encryption_token=token)
        execution = wired.run_managed.execute(command)
    except RunInterrupted as exc:
        # A requested stop, not a failure: nothing was recorded. Exit 130 is the
        # conventional "terminated by Ctrl-C".
        print(f"gmlc: {exc}", file=sys.stderr)
        return 130
    except subprocess.TimeoutExpired as exc:
        # The real call ran past --timeout and was killed before any record. Exit
        # 124 is the timeout(1) convention, distinct from miss (3) and error (4).
        print(
            f"gmlc: real call exceeded the {exc.timeout}s timeout and was killed; nothing recorded",
            file=sys.stderr,
        )
        return 124
    except CacheMiss as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 3
    except (EncryptionTokenRequired, WrongEncryptionToken) as exc:
        print(f"gmlc: {exc} (set --token or GMLCACHE_TOKEN)", file=sys.stderr)
        return 4
    except CacheError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    # Materialise captured files into the cwd, exactly as the real client would.
    _apply_output_files(execution, Path.cwd())

    if getattr(args, "json", False):
        return _print_run_json(execution, command)

    sys.stdout.write(_artifact_text(execution, ArtifactType.STDOUT))
    sys.stdout.flush()
    sys.stderr.write(_artifact_text(execution, ArtifactType.STDERR))
    sys.stderr.flush()
    return _run_exit_code(execution)


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

    from generic_ml_cache_core.adapter.out.client.discover import list_models, list_models_all

    try:
        file_cfg = config.load()
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    if args.client:
        executable = config.executable_for(file_cfg, args.client, flag=args.executable)
        listings = [list_models(args.client, executable=executable, timeout=args.timeout)]
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

    wired = build_use_cases(Path(str(settings["store"][0])))
    summaries = wired.repository.current_execution_summaries()
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


def _cmd_session_start(args: argparse.Namespace) -> int:
    import secrets

    # Print only the id, so it is scriptable: SESSION=$(gmlcache session start)
    print(secrets.token_hex(8))
    return 0


#: events where a real client call ran (vs. HIT, which replayed, or an offline MISS).
_EXECUTED_EVENTS = {"record", "run", "would_hit", "would_miss"}


def _cmd_session_report(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    counts = build_use_cases(store_root).metrics.session_event_counts(args.session_id)
    invocations = sum(counts.values())
    executions = sum(n for event, n in counts.items() if event in _EXECUTED_EVENTS)
    hits = counts.get("hit", 0)

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "session": args.session_id,
                    "invocations": invocations,
                    "executions": executions,
                    "hits": hits,
                    "events": counts,
                },
                indent=2,
            )
        )
        return 0

    if invocations == 0:
        print(f"no events recorded for session {args.session_id!r}")
        return 0
    print(f"session     : {args.session_id}")
    print(f"invocations : {invocations}")
    print(f"executions  : {executions}  (real client calls)")
    print(f"hits        : {hits}  (served from cache)")
    breakdown = ", ".join(f"{event}={counts[event]}" for event in sorted(counts))
    print(f"events      : {breakdown}")
    return 0


def _cmd_session(args: argparse.Namespace) -> int:
    print("usage: gmlcache session start | gmlcache session report <id>", file=sys.stderr)
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


def render_banner(color: bool = False) -> str:
    """The boxed gmlcache banner. Width is derived from the content, so any version
    string or tagline stays aligned. ``color`` adds teal ANSI; off yields plain text."""
    title = "gmlcache"
    ver = __version__
    tag = "record · replay · check · tokens"

    if color:
        rule = _TEAL  # teal box
        name = _BOLD  # bold title
        vers = _TEAL_BRIGHT  # bright-teal version
        sub = _GREY  # dim-grey tagline
        off = _RESET
    else:
        rule = name = vers = sub = off = ""

    left_top = f"─ {title} "
    right_top = f" {ver} ─"
    inner = max(len(left_top) + 6 + len(right_top), len(tag) + 4)
    top_dashes = inner - len(left_top) - len(right_top)
    pad_right = inner - 2 - len(tag)

    top = (
        f"{rule}┌─ {off}{name}{title}{off}"
        f"{rule} {'─' * top_dashes} {off}{vers}{ver}{off}{rule} ─┐{off}"
    )
    mid = f"{rule}│{off}  {sub}{tag}{off}{' ' * pad_right}{rule}│{off}"
    bot = f"{rule}└{'─' * inner}┘{off}"
    return "\n".join([top, mid, bot])


class _BannerParser(argparse.ArgumentParser):
    """An ArgumentParser whose full help is fronted by the banner, so the banner
    shows on ``-h`` and on a bare invocation (but not on terse usage/error lines)."""

    def format_help(self) -> str:
        return render_banner(_use_color()) + "\n\n" + super().format_help()


def build_parser() -> argparse.ArgumentParser:
    parser = _BannerParser(
        prog="gmlcache",
        description="Content-addressed cache/proxy for agentic CLI calls.",
    )
    parser.add_argument("--version", action="version", version=f"gmlcache {__version__}")
    sub = parser.add_subparsers(dest="command", required=False)

    run = sub.add_parser("run", help="resolve a request (record on miss, replay on hit)")
    run.add_argument("--client", required=True, choices=registered_names())
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
    run.add_argument(
        "--mode",
        choices=[m.value for m in CacheMode],
        default=None,
        help="resolution mode (default: cache, or config/env)",
    )
    run.add_argument(
        "--persist",
        choices=[d.value for d in PersistenceDepth],
        default=None,
        help=(
            "how much to keep: meter (usage only, never replays), cache (+output, "
            "the default), or dataset (+input) (default: cache, or config/env)"
        ),
    )
    run.add_argument("--offline", action="store_true", help="shortcut for --mode offline")
    run.add_argument("--force", action="store_true", help="shortcut for --mode refresh")
    run.add_argument(
        "--record-on-error",
        action="store_true",
        help="also cache a call that fails (non-zero exit); default is to store only successes",
    )
    run.add_argument("--executable", help="override the client executable (the seam)")
    run.add_argument(
        "--token", help="encryption token for an encrypted store (or set GMLCACHE_TOKEN)"
    )
    run.add_argument(
        "--session", help="group this run under a session id (or set GMLCACHE_SESSION)"
    )
    run.add_argument(
        "--timeout", type=float, default=None, help="seconds before the real call is killed"
    )
    run.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print cache diagnostics to stderr (breaks exact fidelity)",
    )
    run.set_defaults(func=_cmd_run)

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
        choices=registered_names(),
        help="one client; omit to query every registered client",
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
    session_start.set_defaults(func=_cmd_session_start)
    session_report = session_sub.add_parser("report", help="summarise a session's activity")
    session_report.add_argument("session_id", help="the session id to report on")
    session_report.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    session_report.set_defaults(func=_cmd_session_report)
    session.set_defaults(func=_cmd_session)

    init = sub.add_parser(
        "init",
        help="create the config file in the default location (if absent), then show the store",
    )
    init.set_defaults(func=_cmd_init)

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
