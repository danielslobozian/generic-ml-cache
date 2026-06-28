# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: setup commands — doctor, models, status, init."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generic_ml_cache_cli._compose import get_encryption_state
from generic_ml_cache_core.common.errors import ConfigError, UnknownClient

from generic_ml_cache_cli import config
from generic_ml_cache_cli.composition import _db_conn_factory, _make_diag


def _probe_daemon(host: str, port: int) -> bool:
    """Return True if the daemon /health endpoint responds with HTTP 200."""
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    url = f"http://{host}:{port}/health"  # NOSONAR — localhost daemon, plain HTTP is correct
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
            return int(resp.status) == 200
    except Exception:
        return False


def _doctor_payload(args: argparse.Namespace) -> dict:
    """Collect the full diagnostic payload (no credentials included)."""
    import os  # noqa: PLC0415
    import platform  # noqa: PLC0415
    from dataclasses import asdict  # noqa: PLC0415

    from generic_ml_cache_core.adapter.registry import adapter_sources  # noqa: PLC0415
    from generic_ml_cache_adapters.adapter.out.client.discover import probe_all  # noqa: PLC0415
    from generic_ml_cache_adapters.migration_runner import schema_version  # noqa: PLC0415

    file_cfg = config.load()
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
    ep_sources = adapter_sources(whitelist=file_cfg.adapters)

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)
    store_exists = store_root.exists()

    return {
        "python": sys.version,
        "os": f"{platform.system()} {platform.release()}",
        "config_path": str(config.resolve_config_path()),
        "store_path": str(store_root),
        "store_permissions": {
            "exists": store_exists,
            "readable": os.access(store_root, os.R_OK) if store_exists else False,
            "writable": os.access(store_root, os.W_OK) if store_exists else False,
        },
        "daemon": {
            "host": host,
            "port": port,
            "reachable": _probe_daemon(host, port),
        },
        "clients": [asdict(s) for s in statuses],
        "schema": applied,
        "adapter_extensions": ep_sources,
    }


def _print_doctor_text(payload: dict) -> None:
    import platform  # noqa: PLC0415

    py_short = sys.version.split()[0]
    print(f"python      : {py_short}  ({platform.system()} {platform.release()})")
    print(f"config file : {payload['config_path']}")
    print(f"store path  : {payload['store_path']}")
    perms = payload["store_permissions"]
    if perms["exists"]:
        rw = ("r" if perms["readable"] else "") + ("w" if perms["writable"] else "")
        print(f"store perms : {rw or 'none'}")
    else:
        print("store perms : (not initialised)")
    d = payload["daemon"]
    reach = "reachable" if d["reachable"] else "not running"
    print(f"daemon      : {reach}  ({d['host']}:{d['port']})")
    print()

    statuses_raw = payload["clients"]
    if not statuses_raw:
        print("no client adapters are registered")
    else:
        print("configured clients (advisory — discovery never chooses or gates a run):")
        for s in statuses_raw:
            if s["present"]:
                print(
                    f"  {s['name']:<8} present  {(s.get('version') or 'version unknown'):<28}  {s.get('executable', '')}"
                )
            else:
                print(f"  {s['name']:<8} missing  {s.get('detail') or ''}")

    ep_sources = payload["adapter_extensions"]
    if ep_sources:
        print()
        print("installed adapter extensions:")
        for ep_name, ep_source in sorted(ep_sources.items()):
            print(f"  {ep_name:<8} {ep_source}")

    print()
    applied = payload["schema"]
    if applied:
        latest = applied[-1]
        print(
            f"store schema : {len(applied)} migration(s) applied — {latest['migration_id']}  ({latest['applied_at_utc']})"
        )
    else:
        print("store schema : not initialised (run any gmlcache command to apply migrations)")


def _cmd_doctor(args: argparse.Namespace) -> int:
    import json  # noqa: PLC0415

    try:
        payload = _doctor_payload(args)
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    if getattr(args, "bundle", False):
        from datetime import datetime, timezone  # noqa: PLC0415

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bundle_path = Path(f"gmlcache-bundle-{ts}.json")
        bundle_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"bundle written: {bundle_path.resolve()}")
        return 0

    _print_doctor_text(payload)
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

    from generic_ml_cache_adapters.adapter.out.api.api_discover import list_api_models
    from generic_ml_cache_adapters.adapter.out.client.discover import list_models, list_models_all

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
