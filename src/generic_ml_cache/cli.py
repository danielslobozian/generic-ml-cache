# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Command-line interface for generic-ml-cache.

    gmlcache run     -- resolve a request (record on miss, replay on hit)
    gmlcache doctor  -- report which configured clients are present (advisory)
    gmlcache models  -- list a client's available models (advisory; relayed)
    gmlcache inspect -- pretty-print a cassette

Replay fidelity: in the default (quiet) mode, ``run`` reproduces the client's
stdout, stderr and exit code exactly. Cache diagnostics appear only with
``-v/--verbose`` and are written to stderr with a ``gmlc:`` prefix, which by
design breaks byte-exact stderr fidelity -- use quiet mode when that matters.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .adapters.registry import registered_names
from .cache import Mode, Request, apply_response, resolve
from .errors import CacheError, CacheMiss
from .store import CassetteStore

DEFAULT_STORE = ".gmlcache"


def _read_text_arg(inline: Optional[str], path: Optional[str], name: str) -> str:
    if inline is not None and path is not None:
        raise SystemExit(f"error: pass only one of --{name} / --{name}-file")
    if path is not None:
        return Path(path).read_text(encoding="utf-8")
    return inline if inline is not None else ""


def _mode_from_args(args: argparse.Namespace) -> Mode:
    if args.offline:
        return Mode.OFFLINE
    if args.force:
        return Mode.REFRESH
    return Mode(args.mode)


def _cmd_run(args: argparse.Namespace) -> int:
    context = _read_text_arg(args.context, args.context_file, "context")
    prompt = _read_text_arg(args.prompt, args.prompt_file, "prompt")
    if not prompt:
        raise SystemExit("error: a non-empty --prompt or --prompt-file is required")

    system_prompt = (
        _read_text_arg(args.system_prompt, args.system_prompt_file, "system-prompt") or None
    )

    request = Request(
        client=args.client,
        model=args.model,
        effort=args.effort,
        context=context,
        prompt=prompt,
        user_system_prompt=system_prompt,
    )
    store = CassetteStore(Path(args.store))
    mode = _mode_from_args(args)

    def log(msg: str) -> None:
        if args.verbose:
            print(f"gmlc: {msg}", file=sys.stderr)

    try:
        outcome = resolve(
            request,
            store,
            mode=mode,
            executable=args.executable,
            timeout=args.timeout,
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

    statuses = probe_all(timeout=args.timeout)

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

    if args.client:
        listings = [list_models(args.client, executable=args.executable, timeout=args.timeout)]
    else:
        listings = list_models_all(timeout=args.timeout)

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
    run.add_argument("--effort", required=True)
    run.add_argument("--prompt")
    run.add_argument("--prompt-file")
    run.add_argument("--context")
    run.add_argument("--context-file")
    run.add_argument("--system-prompt")
    run.add_argument("--system-prompt-file")
    run.add_argument(
        "--store", default=DEFAULT_STORE, help=f"cassette directory (default: {DEFAULT_STORE})"
    )
    run.add_argument("--mode", choices=[m.value for m in Mode], default=Mode.CACHE.value)
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

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
