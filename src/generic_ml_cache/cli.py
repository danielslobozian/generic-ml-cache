# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
# PYTHON_ARGCOMPLETE_OK
"""Command-line interface for generic-ml-cache.

    gmlcache run     -- resolve a request (record on miss, replay on hit)
    gmlcache doctor  -- report which configured clients are present (advisory)
    gmlcache models  -- list a client's available models (advisory; relayed)
    gmlcache status  -- show the resolved configuration and where it came from
    gmlcache init    -- create the config file in the default location (if absent)
    gmlcache inspect -- pretty-print a cassette

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

from generic_ml_cache.adapter.inbound.composition import build_use_cases
from generic_ml_cache.adapter.out.client.registry import registered_names
from generic_ml_cache.application.domain.model.artifact import ArtifactType
from generic_ml_cache.application.domain.model.cache_mode import CacheMode
from generic_ml_cache.application.domain.model.execution_state import ExecutionState
from generic_ml_cache.application.domain.model.ml_execution import MlExecution
from generic_ml_cache.application.port.inbound.run_managed_local_execution_command import (
    RunManagedLocalExecutionCommand,
)
from generic_ml_cache.application.port.out.base import ClientAdapter
from generic_ml_cache.common.errors import CacheError, CacheMiss, ConfigError, RunInterrupted

from . import __version__, config

#: capabilities a caller may open with --grant, sourced from the adapter seam so
#: the CLI choices, the help, and what the adapters implement can never drift.
GRANT_CHOICES: List[str] = list(ClientAdapter.GRANTS)
_GRANT_HELP = (
    "open a capability for the client -- enablement, not restriction. One of "
    "{net, read, write, shell, web-search}: net reaches the web, read/write/shell "
    "widen file and command access, web-search enables the search tool. Part of "
    "the key (a granted call is its own cassette) and cacheable like any call; use "
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
        settings = config.resolve_settings(file_cfg, mode_flag=args.mode, timeout_flag=args.timeout)
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
        record_on_error=args.record_on_error,
    )

    def executable_override(client: str):
        return config.executable_for(file_cfg, client, flag=args.executable)

    wired = build_use_cases(store_root, executable_override, timeout)

    try:
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

    from generic_ml_cache.application.domain.model.probe_status import ProbeStatus
    from generic_ml_cache.application.port.inbound.probe_command import ProbeCommand

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

    print(f"status  : {report.status.value}")
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

    from generic_ml_cache.adapter.out.client.discover import probe_all

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

    from generic_ml_cache.adapter.out.client.discover import list_models, list_models_all

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

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "config_file": str(path),
                    "loaded": loaded,
                    "settings": {k: {"value": v[0], "source": v[1]} for k, v in settings.items()},
                    "executables": dict(file_cfg.executables),
                },
                indent=2,
            )
        )
        return 0

    print(f"config file : {path}  ({'loaded' if loaded else 'not present'})")
    print("effective settings (no run flags applied):")
    for key in ("mode", "store", "timeout", "trust_scan", "max_size"):
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
    print(f"cassette store: {value}  (from {source})")
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

    print(f"executions : {len(summaries)}")
    if by_client_model:
        print("by client / model:")
        for (client, model), count in sorted(by_client_model.items()):
            print(f"  {client:<8} {model:<26} {count:>5}")
    if access:
        parts = ", ".join(f"{event}={count}" for event, count in sorted(access.items()))
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
        }
        for summary in wired.repository.current_execution_summaries()
        if (not args.client or summary.client == args.client)
        and (not args.model or summary.model == args.model)
    ]

    if args.json:
        print(json.dumps({"executions": entries}, indent=2))
        return 0

    if not entries:
        print("no current executions")
        return 0

    print(f"executions : {len(entries)}")
    for entry in sorted(entries, key=lambda item: (item["client"], item["model"], item["key"])):
        print(
            f"  {entry['client']:<8} {entry['model']:<20} {entry['kind']:<18} "
            f"{entry['key'][:12]}  hits:{entry['hits']}"
        )
    return 0


def _use_color() -> bool:
    """Colour only when writing to a real terminal and NO_COLOR is unset, so piped
    or redirected output never carries escape codes (the conventional contract)."""
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def render_banner(color: bool = False) -> str:
    """The boxed gmlcache banner. Width is derived from the content, so any version
    string or tagline stays aligned. ``color`` adds teal ANSI; off yields plain text."""
    title = "gmlcache"
    ver = __version__
    tag = "record · replay · check · tokens"

    if color:
        rule = "\x1b[38;5;37m"  # teal box
        name = "\x1b[1m"  # bold title
        vers = "\x1b[38;5;43m"  # bright-teal version
        sub = "\x1b[38;5;245m"  # dim-grey tagline
        off = "\x1b[0m"
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
            "(different args = different cassette); only its fingerprint is stored, "
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
    run.add_argument("--offline", action="store_true", help="shortcut for --mode offline")
    run.add_argument("--force", action="store_true", help="shortcut for --mode refresh")
    run.add_argument(
        "--record-on-error",
        action="store_true",
        help="also cache a call that fails (non-zero exit); default is to store only successes",
    )
    run.add_argument("--executable", help="override the client executable (the seam)")
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
    inspect.add_argument(
        "execution", help="an execution key, or a short prefix as shown by `list`"
    )
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
        help="show how many cassettes are stored, their total size split by client/model, "
        "and access counts",
    )
    stats.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    stats.set_defaults(func=_cmd_stats)

    listp = sub.add_parser(
        "list", help="list stored cassettes, grouped by client/model (read-only)"
    )
    listp.add_argument("--client", help="only cassettes recorded for this client")
    listp.add_argument("--model", help="only cassettes recorded for this model")
    listp.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    listp.set_defaults(func=_cmd_list)

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
