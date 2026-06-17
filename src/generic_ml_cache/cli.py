# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
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
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import __version__, config
from .adapters.registry import registered_names
from .cache import Mode, Request, apply_response, resolve
from .errors import CacheError, CacheMiss, ConfigError, RunInterrupted
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

    # Declared scan folders (allow-path): validated directories, normalised to abs.
    allow_paths: List[str] = []
    for raw in args.allow_path or []:
        p = Path(raw)
        if not p.is_dir():
            raise SystemExit(f"error: allow-path is not a directory: {raw}")
        allow_paths.append(str(p.resolve()))

    request = Request(
        client=args.client,
        model=args.model,
        effort=args.effort,
        context=context,
        prompt=prompt,
        user_system_prompt=system_prompt,
        input_files=input_files,
        allow_paths=allow_paths,
    )
    try:
        file_cfg = config.load()
        settings = config.resolve_settings(
            file_cfg,
            mode_flag=args.mode,
            timeout_flag=args.timeout,
        )
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    max_size = settings["max_size"][0]
    store = CassetteStore(
        Path(str(settings["store"][0])),
        max_bytes=int(max_size) if max_size is not None else None,
    )
    timeout = settings["timeout"][0]
    trust_scan = bool(settings["trust_scan"][0])
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
            trust_scan=trust_scan,
            record_on_error=args.record_on_error,
        )
    except RunInterrupted as exc:
        # A requested stop, not a failure: no cassette was written. Exit code 130
        # (the conventional "terminated by Ctrl-C") tells the caller it was stopped.
        print(f"gmlc: {exc}", file=sys.stderr)
        return 130
    except subprocess.TimeoutExpired as exc:
        # The real call ran past --timeout and was killed; the unwinding happened
        # before any cassette write, so nothing was stored. Exit 124 is the
        # `timeout(1)` convention for "command timed out", distinct from miss (3)
        # and error (4).
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

    if outcome.hit:
        log("cache hit; replaying cassette")
    elif outcome.passthrough:
        log("allow-path call — ran fresh, stored nothing (not cacheable)")
    elif outcome.failed_unstored:
        log(
            f"real call failed (exit {outcome.response.exit}); not cached "
            "(pass --record-on-error to store failures)"
        )
    elif outcome.recorded:
        log(f"recorded real call -> cassette {outcome.cassette.match_key}.json")

    # The cache writes produced files into the directory it was called in,
    # exactly as the real client would. There is no output-dir knob: to put the
    # outputs elsewhere, run the cache there -- same as you would the client.
    apply_response(outcome.response, Path.cwd())

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
    usage = cassette.response.usage
    if usage is None:
        print("usage  : (none captured)")
    else:
        print(f"usage  : {_usage_summary(usage)}")
        if usage.cost_usd is not None:
            print(f"         cost ~ ${usage.cost_usd:.4f} (client estimate, not authoritative)")
        if args.raw:
            import json as _json

            print("raw usage (verbatim from the client):")
            print(_indent(_json.dumps(usage.raw, indent=2, sort_keys=True), "         "))
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


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


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


def _indent(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _tokens_saved(hit_counts: dict, usage_by_key: dict) -> dict:
    """Sum the usage that cache hits avoided spending.

    Each hit on a cassette would otherwise have been a real call costing that
    cassette's recorded usage, so the saving is ``usage * hits`` summed over
    cassettes. A field stays ``None`` ("unknown") if no contributing cassette
    reported it -- never silently 0. Hits whose cassette is gone or carried no
    usage are counted separately so the figure is not quietly understated.
    """
    fields = ("input_tokens", "output_tokens", "cache_read_tokens")
    sums = {f: 0 for f in fields}
    known = {f: False for f in fields}
    cost_sum = 0.0
    cost_known = False
    replays = 0
    replays_without_usage = 0
    for key, hits in hit_counts.items():
        usage = usage_by_key.get(key)
        if usage is None:
            replays_without_usage += hits
            continue
        replays += hits
        for f in fields:
            value = getattr(usage, f)
            if value is not None:
                sums[f] += value * hits
                known[f] = True
        if usage.cost_usd is not None:
            cost_sum += usage.cost_usd * hits
            cost_known = True
    return {
        "replays": replays,
        "replays_without_usage": replays_without_usage,
        "input_tokens": sums["input_tokens"] if known["input_tokens"] else None,
        "output_tokens": sums["output_tokens"] if known["output_tokens"] else None,
        "cache_read_tokens": sums["cache_read_tokens"] if known["cache_read_tokens"] else None,
        "cost_usd": cost_sum if cost_known else None,
    }


def _cmd_stats(args: argparse.Namespace) -> int:
    import json

    from .cassette import Cassette

    try:
        settings = config.resolve_settings(config.load())
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    store = CassetteStore(Path(str(settings["store"][0])))
    root = store.root

    # Tally cassettes by (client, model). stats is an occasional, explicit call,
    # so reading each cassette to learn its client/model is fine; a corrupt or
    # unreadable file is skipped rather than aborting the report.
    by_client_model: Dict[tuple, List[int]] = {}
    usage_by_key: Dict[str, object] = {}
    total_count = 0
    total_bytes = 0
    if root.exists():
        for path in sorted(root.glob("*.json")):
            try:
                size = path.stat().st_size
                cassette = Cassette.from_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            slot = by_client_model.setdefault((cassette.client, cassette.model), [0, 0])
            slot[0] += 1
            slot[1] += size
            total_count += 1
            total_bytes += size
            if cassette.response.usage is not None:
                usage_by_key[cassette.match_key] = cassette.response.usage

    access = store.registry.event_counts()
    saved = _tokens_saved(store.registry.hit_counts_by_key(), usage_by_key)

    if args.json:
        print(
            json.dumps(
                {
                    "store": str(root),
                    "cassettes": total_count,
                    "bytes": total_bytes,
                    "by_client_model": [
                        {"client": client, "model": model, "cassettes": n, "bytes": b}
                        for (client, model), (n, b) in sorted(by_client_model.items())
                    ],
                    "access_events": access,
                    "tokens_saved": saved,
                },
                indent=2,
            )
        )
        return 0

    print(f"store     : {root}")
    print(f"cassettes : {total_count}  ({_human_size(total_bytes)} total)")
    if by_client_model:
        print("by client / model:")
        for (client, model), (n, b) in sorted(by_client_model.items()):
            print(f"  {client:<8} {model:<26} {n:>5}  {_human_size(b)}")
    if access:
        parts = ", ".join(f"{event}={count}" for event, count in sorted(access.items()))
        print(f"access    : {parts}")
    else:
        print("access    : (no events recorded yet)")

    if saved["replays"] == 0:
        print("saved     : (no replays yet — savings appear once cassettes are reused)")
    else:
        print(
            f"saved     : from {saved['replays']} replay(s) — "
            f"input {_token_str(saved['input_tokens'])}, "
            f"output {_token_str(saved['output_tokens'])}, "
            f"cache-read {_token_str(saved['cache_read_tokens'])} tokens"
        )
        if saved["cost_usd"] is not None:
            print(
                f"            ~ ${saved['cost_usd']:.4f} (from client cost estimates; "
                "not authoritative)"
            )
        if saved["replays_without_usage"]:
            print(
                f"            ({saved['replays_without_usage']} replay(s) had no recorded "
                "usage and are not counted)"
            )
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
        "--mode",
        choices=[m.value for m in Mode],
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

    inspect = sub.add_parser("inspect", help="pretty-print a cassette")
    inspect.add_argument("cassette", help="path to a cassette JSON file")
    inspect.add_argument(
        "--raw",
        action="store_true",
        help="also print the client's verbatim usage block (as the client reported it)",
    )
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

    stats = sub.add_parser(
        "stats",
        help="show how many cassettes are stored, their total size split by client/model, "
        "and access counts",
    )
    stats.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    stats.set_defaults(func=_cmd_stats)

    init = sub.add_parser(
        "init",
        help="create the config file in the default location (if absent), then show the store",
    )
    init.set_defaults(func=_cmd_init)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
