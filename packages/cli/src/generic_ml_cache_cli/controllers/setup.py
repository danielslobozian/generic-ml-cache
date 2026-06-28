# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: setup commands — doctor, models, status, init."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generic_ml_cache_core.adapter.inbound.composition import get_encryption_state
from generic_ml_cache_core.common.errors import ConfigError, UnknownClient

from generic_ml_cache_cli import config
from generic_ml_cache_cli.composition import _db_conn_factory, _make_diag


def _cmd_doctor(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from generic_ml_cache_core.adapter.inbound.composition import probe_all, schema_version

    try:
        file_cfg = config.load()
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    settings = config.resolve_settings(file_cfg)
    store_root = Path(str(settings["store"][0]))
    _diag = _make_diag(args)
    applied = schema_version(_db_conn_factory(store_root), diag=_diag)

    statuses = probe_all(
        timeout=args.timeout,
        executables=file_cfg.executables,
        whitelist=file_cfg.adapters,
        diag=_diag,
    )

    if args.json:
        import json

        print(json.dumps({"clients": [asdict(s) for s in statuses], "schema": applied}, indent=2))
        return 0

    if not statuses:
        print("no client adapters are registered")
    else:
        print("configured clients (advisory — discovery never chooses or gates a run):")
        for s in statuses:
            if s.present:
                print(
                    f"  {s.name:<8} present  {(s.version or 'version unknown'):<28}  {s.executable}"
                )
            else:
                print(f"  {s.name:<8} missing  {s.detail or ''}")

    print()
    if applied:
        latest = applied[-1]
        print(
            f"store schema : {len(applied)} migration(s) applied — {latest['migration_id']}  ({latest['applied_at_utc']})"
        )
    else:
        print("store schema : not initialised (run any gmlcache command to apply migrations)")
    return 0


def _print_model_listing(ml) -> None:
    if not ml.present:
        print(f"  {ml.name:<8} absent   {ml.reason or ''}")
        return
    if not ml.supported:
        print(f"  {ml.name:<8} —        {ml.reason or 'model listing not supported'}")
        return
    if ml.models is None:
        print(f"  {ml.name:<8} —        {ml.reason or 'could not list models'}")
        return
    print(f"  {ml.name:<8} {len(ml.models)} model(s) (advisory; relayed from the client):")
    for m in ml.models:
        if m.default:
            marker = " (default)"
        elif m.current:
            marker = " (current)"
        else:
            marker = ""
        print(f"      {m.id:<34} {m.name}{marker}")


def _cmd_models(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from generic_ml_cache_core.adapter.inbound.composition import (
        list_api_models,
        list_models,
        list_models_all,
    )

    try:
        file_cfg = config.load()
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    _diag = _make_diag(args)
    if args.client:
        executable = config.executable_for(file_cfg, args.client, flag=args.executable)
        try:
            listings = [
                list_models(
                    args.client,
                    executable=executable,
                    timeout=args.timeout,
                    whitelist=file_cfg.adapters,
                    diag=_diag,
                )
            ]
        except UnknownClient:
            # Not a local managed adapter — try the API provider registry.
            listings = [list_api_models(args.client, whitelist=file_cfg.adapters)]
    else:
        listings = list_models_all(
            timeout=args.timeout,
            executables=file_cfg.executables,
            whitelist=file_cfg.adapters,
            diag=_diag,
        )

    if args.json:
        import json

        # Always valid JSON on every path (absent / unsupported / listed), so a
        # caller can parse the output unconditionally.
        print(json.dumps([asdict(m) for m in listings], indent=2))
        return 0

    for ml in listings:
        _print_model_listing(ml)
    return 0


def _print_status_text(settings, file_cfg, path, loaded, encryption, adapters_whitelist) -> None:
    print(f"config file : {path}  ({'loaded' if loaded else 'not present'})")
    print(f"encryption  : {encryption}")
    print("effective settings (no run flags applied):")
    for key in ("mode", "persist", "store", "timeout", "trust_scan", "max_size", "max_age"):
        value, source = settings[key]
        shown = "none" if value is None else value
        if isinstance(shown, bool):
            shown = "true" if shown else "false"
        print(f"  {key:<10} {str(shown):<14} (from {source})")
    if adapters_whitelist is None:
        print("adapters    : * (all active)")
    else:
        print(f"adapters    : {', '.join(adapters_whitelist)} (from config)")
    if file_cfg.executables:
        print("executables (from config; --executable still overrides per call):")
        for client, exe in file_cfg.executables.items():
            print(f"  {client:<8} {exe}")
    else:
        print("executables : none configured (clients resolved on PATH)")


def _cmd_status(args: argparse.Namespace) -> int:
    try:
        file_cfg = config.load()
        settings = config.resolve_settings(file_cfg)  # no run flags: env > file > default
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    path = config.resolve_config_path()
    loaded = file_cfg.source is not None
    encryption = get_encryption_state(Path(str(settings["store"][0]))).value
    adapters_whitelist = sorted(file_cfg.adapters) if file_cfg.adapters is not None else None

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "config_file": str(path),
                    "loaded": loaded,
                    "encryption": encryption,
                    "settings": {k: {"value": v[0], "source": v[1]} for k, v in settings.items()},
                    "adapters": adapters_whitelist,
                    "executables": dict(file_cfg.executables),
                },
                indent=2,
            )
        )
        return 0

    _print_status_text(settings, file_cfg, path, loaded, encryption, adapters_whitelist)
    return 0


def _cmd_init(_args: argparse.Namespace) -> int:
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
