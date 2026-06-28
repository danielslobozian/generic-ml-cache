# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: daemon sub-commands — start, stop, status, status-line."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from generic_ml_cache_cli import config
from generic_ml_cache_cli.composition import _store_root


def _cmd_daemon(args: argparse.Namespace) -> int:
    print("usage: gmlcache daemon {start,stop,status}", file=sys.stderr)
    return 1


def _cmd_daemon_start(args: argparse.Namespace) -> int:
    try:
        from generic_ml_cache_daemon.app import create_app  # noqa: PLC0415
    except ImportError:
        print(
            "error: generic-ml-cache-daemon is not installed. "
            "Install it with: pip install generic-ml-cache-daemon",
            file=sys.stderr,
        )
        return 1
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:
        print("error: uvicorn is not installed (install generic-ml-cache-daemon)", file=sys.stderr)
        return 1

    store_root = _store_root()
    if store_root is None:
        return 4

    session_id: Optional[str] = getattr(args, "session", None) or None
    enable_metrics: bool = getattr(args, "metrics", False)
    host: str = args.host
    port: int = args.port

    _daemon_cfg = config.load()
    settings = config.resolve_settings(_daemon_cfg)
    max_size: Optional[int] = settings["max_size"][0]  # type: ignore[assignment]
    max_age: Optional[float] = settings["max_age"][0]  # type: ignore[assignment]

    application = create_app(
        store_root,
        session_id=session_id,
        enable_metrics=enable_metrics,
        max_size=max_size,
        max_age=max_age,
        whitelist=_daemon_cfg.adapters,
    )
    uvicorn.run(application, host=host, port=port)
    return 0


def _cmd_daemon_status(args: argparse.Namespace) -> int:
    import json as _json  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    host: str = args.host
    port: int = args.port
    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
            data = _json.loads(resp.read())
            status = data.get("status", "unknown")
    except urllib.error.URLError:
        status = "not running"
        if not getattr(args, "json", False):
            print(f"daemon: {status}")
            return 1

    if getattr(args, "json", False):
        import json as _json2  # noqa: PLC0415

        print(_json2.dumps({"status": status, "host": host, "port": port}))
    else:
        print(f"daemon: {status} (http://{host}:{port})")
    return 0 if status == "ok" else 1


def _cmd_daemon_stop(args: argparse.Namespace) -> int:
    import signal  # noqa: PLC0415
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    host: str = args.host
    port: int = args.port
    health_url = f"http://{host}:{port}/health"
    try:
        urllib.request.urlopen(health_url, timeout=3)  # noqa: S310
    except urllib.error.URLError:
        print("daemon: not running", file=sys.stderr)
        return 1

    store_root = _store_root()
    pid_path = (store_root / ".daemon.pid") if store_root else None
    if pid_path is None or not pid_path.exists():
        print("daemon: running but no PID file found — send SIGTERM manually", file=sys.stderr)
        return 1

    try:
        pid = int(pid_path.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        pid_path.unlink(missing_ok=True)
        print(f"daemon: sent SIGTERM to PID {pid}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"daemon: failed to stop — {exc}", file=sys.stderr)
        return 1


def _cmd_status_line(args: argparse.Namespace) -> int:
    """Emit live session stats as JSON for status-bar integrations.

    Designed to be called repeatedly by a status-bar formatter script.  Exits 0
    and prints nothing when no session is active or the daemon is not running —
    the caller decides how to handle absence.
    """
    import urllib.error  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415

    session_id: Optional[str] = getattr(args, "session", None) or os.environ.get("GMLCACHE_SESSION")
    if not session_id:
        return 0

    host: str = args.host
    port: int = args.port
    stats_url = f"http://{host}:{port}/sessions/{session_id}/stats"  # NOSONAR
    try:
        with urllib.request.urlopen(stats_url, timeout=2) as response:  # noqa: S310
            print(response.read().decode())
    except (urllib.error.URLError, OSError):
        pass
    return 0
