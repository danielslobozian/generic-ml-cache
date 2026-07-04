# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: setup commands — doctor, models, status, init."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, cast

from generic_ml_cache_core.common.errors import ConfigError, UnknownClient

from generic_ml_cache_cli import config
from generic_ml_cache_cli._compose import get_encryption_state
from generic_ml_cache_cli.composition import db_conn_factory, make_diag

if TYPE_CHECKING:
    from generic_ml_cache_bootstrap.discovery.client_discover import ModelListing


class _StorePermissions(TypedDict):
    """The doctor's store-permission probe results."""

    exists: bool
    readable: bool
    writable: bool


class _DaemonReachability(TypedDict):
    """The doctor's daemon-liveness probe results."""

    host: str
    port: int
    reachable: bool


class _DoctorPayload(TypedDict):
    """The full doctor diagnostic payload (also the --json / --bundle shape)."""

    python: str
    os: str
    config_path: str
    store_path: str
    store_permissions: _StorePermissions
    daemon: _DaemonReachability
    clients: list[dict[str, Any]]
    schema: list[dict[str, object]]
    adapter_extensions: dict[str, str]


def _probe_daemon(host: str, port: int) -> bool:
    """Return True if the daemon /health endpoint responds with HTTP 200."""
    import urllib.request

    url = f"http://{host}:{port}/health"  # NOSONAR — localhost daemon, plain HTTP is correct
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
            return int(resp.status) == 200
    except Exception:  # noqa: BLE001 — liveness probe: any failure means "daemon not reachable"
        return False


def _doctor_payload(args: argparse.Namespace) -> _DoctorPayload:
    """Collect the full diagnostic payload (no credentials included)."""
    import os
    import platform
    from dataclasses import asdict

    from generic_ml_cache_adapters.migration_runner import schema_version
    from generic_ml_cache_bootstrap.discovery.client_discover import probe_all

    from generic_ml_cache_cli.discovery import adapter_sources

    file_cfg = config.load()
    settings = config.resolve_settings(file_cfg)
    store_root = Path(str(settings["store"][0]))
    _diag = make_diag(args)

    # schema_version's own annotation is the unparametrized `list[dict]`; the cast
    # pins the JSON-shaped rows the migration runner actually returns.
    applied = cast(
        "list[dict[str, object]]", schema_version(db_conn_factory(store_root), diag=_diag)
    )
    statuses = probe_all(
        timeout=args.timeout,
        executables=file_cfg.executables,
        whitelist=file_cfg.adapters,
        diag=_diag,
    )
    ep_sources = adapter_sources(whitelist=file_cfg.adapters)

    host = str(getattr(args, "host", "127.0.0.1"))
    port = int(getattr(args, "port", 8765))
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


def _print_doctor_text(payload: _DoctorPayload) -> None:
    import platform

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
    daemon_probe = payload["daemon"]
    reach = "reachable" if daemon_probe["reachable"] else "not running"
    print(f"daemon      : {reach}  ({daemon_probe['host']}:{daemon_probe['port']})")
    print()

    statuses_raw = payload["clients"]
    if not statuses_raw:
        print("no client adapters are registered")
    else:
        print("configured clients (advisory — discovery never chooses or gates a run):")
        for client_status in statuses_raw:
            if client_status["present"]:
                print(
                    f"  {client_status['name']:<8} present  "
                    f"{(client_status.get('version') or 'version unknown'):<28}  "
                    f"{client_status.get('executable', '')}"
                )
            else:
                print(f"  {client_status['name']:<8} missing  {client_status.get('detail') or ''}")

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


def cmd_doctor(args: argparse.Namespace) -> int:
    import json

    try:
        payload = _doctor_payload(args)
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    if getattr(args, "bundle", False):
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bundle_path = Path(f"gmlcache-bundle-{ts}.json")
        bundle_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"bundle written: {bundle_path.resolve()}")
        return 0

    _print_doctor_text(payload)
    return 0


def _print_model_listing(listing: ModelListing) -> None:
    if not listing.present:
        print(f"  {listing.name:<8} absent   {listing.reason or ''}")
        return
    if not listing.supported:
        print(f"  {listing.name:<8} —        {listing.reason or 'model listing not supported'}")
        return
    if listing.models is None:
        print(f"  {listing.name:<8} —        {listing.reason or 'could not list models'}")
        return
    print(
        f"  {listing.name:<8} {len(listing.models)} model(s) (advisory; relayed from the client):"
    )
    for model in listing.models:
        if model.default:
            marker = " (default)"
        elif model.current:
            marker = " (current)"
        else:
            marker = ""
        print(f"      {model.id:<34} {model.name}{marker}")


def cmd_models(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from generic_ml_cache_bootstrap.discovery.api_discover import list_api_models
    from generic_ml_cache_bootstrap.discovery.client_discover import list_models, list_models_all

    try:
        file_cfg = config.load()
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    _diag = make_diag(args)
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
        print(json.dumps([asdict(listing) for listing in listings], indent=2))
        return 0

    for listing in listings:
        _print_model_listing(listing)
    return 0


def _print_status_text(
    settings: Mapping[str, tuple[object, str]],
    file_cfg: config.FileConfig,
    path: Path,
    loaded: bool,
    encryption: str,
    adapters_whitelist: list[str] | None,
) -> None:
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


def cmd_status(args: argparse.Namespace) -> int:
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


def cmd_init(_args: argparse.Namespace) -> int:
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
