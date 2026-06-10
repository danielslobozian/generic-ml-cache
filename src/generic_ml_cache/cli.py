# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Command-line interface for generic-ml-cache.

    gmlcache run     -- resolve a request (record on miss, replay on hit)
    gmlcache doctor  -- report which configured clients are present (advisory)
    gmlcache models  -- list a client's available models (advisory; relayed)
    gmlcache status  -- show the resolved configuration and where it came from
    gmlcache inspect -- pretty-print a cassette

Replay fidelity: in the default (quiet) mode, ``run`` reproduces the client's
stdout, stderr and exit code exactly. Cache diagnostics appear only with
``-v/--verbose`` and are written to stderr with a ``gmlc:`` prefix, which by
design breaks byte-exact stderr fidelity -- use quiet mode when that matters.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__, config
from .adapters.registry import registered_names
from .cache import Mode, Request, apply_response, resolve
from .errors import CacheError, CacheMiss, ConfigError
from .store import CassetteStore


def _read_text_arg(inline: Optional[str], path: Optional[str], name: str) -> str:
    if inline is not None and path is not None:
        raise SystemExit(f"error: pass only one of --{name} / --{name}-file")
    if path is not None:
        return Path(path).read_text(encoding="utf-8")
    return inline if inline is not None else ""


def _cmd_run(args: argparse.Namespace) -> int:
    context = _read_text_arg(args.context, args.context_file, "context")
    prompt = _read_text_arg(args.prompt, args.prompt_file, "prompt")
    if not prompt:
        raise SystemExit("error: a non-empty --prompt or --prompt-file is required")

    system_prompt = (
        _read_text_arg(args.system_prompt, args.system_prompt_file, "system-prompt") or None
    )

    # Declared input files: fingerprint each by content (any file type) -> {abs_path: sha}.
    input_files: Dict[str, str] = {}
    for raw in args.input_file or []:
        p = Path(raw)
        if not p.is_file():
            raise SystemExit(f"error: input file not found: {raw}")
        try:
            data = p.read_bytes()
        except OSError as exc:
            raise SystemExit(f"error: cannot read input file {raw}: {exc}")
        input_files[str(p.resolve())] = hashlib.sha256(data).hexdigest()

    request = Request(
        client=args.client,
        model=args.model,
        effort=args.effort,
        context=context,
        prompt=prompt,
        user_system_prompt=system_prompt,
        input_files=input_files,
    )
    try:
        file_cfg = config.load()
        settings = config.resolve_settings(
            file_cfg,
            mode_flag=args.mode,
            store_flag=args.store,
            timeout_flag=args.timeout,
        )
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store = CassetteStore(Path(str(settings["store"][0])))
    timeout = settings["timeout"][0]
    # --offline / --force are explicit flags and win over the resolved mode.
    if args.offline:
        mode = Mode.OFFLINE
    elif args.force:
        mode = Mode.REFRESH
    else:
        mode = Mode(str(settings["mode"][0]))

    def log(msg: str) -> None:
        if args.verbose:
            print(f"gmlc: {msg}", file=sys.stderr)

    try:
        outcome = resolve(
            request,
            store,
            mode=mode,
            executable=config.executable_for(file_cfg, args.client, flag=args.executable),
            timeout=timeout,
        )
    except CacheMiss as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 3
    except CacheError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    if outcome.hit:
        log("cache hit; replaying cassette")
    elif outcome.recorded:
        log(f"recorded real call -> cassette {outcome.cassette.match_key}.json")

    output_dir = Path(args.output_dir) if args.output_dir else Path.cwd()
    apply_response(outcome.response, output_dir)

    # Reproduce the client's streams exactly.
    sys.stdout.write(outcome.response.stdout)
    sys.stdout.flush()
    sys.stderr.write(outcome.response.stderr)
    sys.stderr.flush()
    return outcome.response.exit


def _cmd_inspect(args: argparse.Namespace) -> int:
    from .cassette import Cassette

    text = Path(args.cassette).read_text(encoding="utf-8")
    cassette = Cassette.from_json(text)
    d = cassette.to_dict()
    print(f"client : {d['client']}")
    print(f"model  : {d['model']}")
    print(f"effort : {d['effort']}")
    print(f"checksum: {d['input_checksum']}")
    print(f"key    : {cassette.match_key}")
    print(f"context: {len(cassette.input_data.get('context', ''))} chars")
    print(f"prompt : {len(cassette.input_data.get('prompt', ''))} chars")
    infiles = sorted(k for k in cassette.input_data if k.startswith("input_file:"))
    if infiles:
        print(f"input files: {len(infiles)} (fingerprints)")
        for k in infiles:
            print(f"         - {k[len('input_file:') :][:12]}…")
    print(f"exit   : {cassette.response.exit}")
    print(f"stdout : {len(cassette.response.stdout)} chars")
    print(f"stderr : {len(cassette.response.stderr)} chars")
    print(f"files  : {len(cassette.response.files)}")
    for f in cassette.response.files:
        print(f"         - {f.path} ({f.encoding}, {len(f.content)} chars)")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from .discover import probe_all

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

    from .discover import list_models, list_models_all

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
    for key in ("mode", "store", "timeout"):
        value, source = settings[key]
        shown = "none" if value is None else value
        print(f"  {key:<8} {str(shown):<14} (from {source})")
    if file_cfg.executables:
        print("executables (from config; --executable still overrides per call):")
        for client, exe in file_cfg.executables.items():
            print(f"  {client:<8} {exe}")
    else:
        print("executables : none configured (clients resolved on PATH)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmlcache",
        description="Content-addressed cache/proxy for agentic CLI calls.",
    )
    parser.add_argument("--version", action="version", version=f"gmlcache {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

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
        "--store",
        default=None,
        help="cassette directory (default: .gmlcache, or config/env)",
    )
    run.add_argument(
        "--mode",
        choices=[m.value for m in Mode],
        default=None,
        help="resolution mode (default: cache, or config/env)",
    )
    run.add_argument("--offline", action="store_true", help="shortcut for --mode offline")
    run.add_argument("--force", action="store_true", help="shortcut for --mode refresh")
    run.add_argument("--executable", help="override the client executable (the seam)")
    run.add_argument("--output-dir", help="where replayed files are written (default: CWD)")
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

    inspect = sub.add_parser("inspect", help="pretty-print a cassette")
    inspect.add_argument("cassette", help="path to a cassette JSON file")
    inspect.set_defaults(func=_cmd_inspect)

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

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
