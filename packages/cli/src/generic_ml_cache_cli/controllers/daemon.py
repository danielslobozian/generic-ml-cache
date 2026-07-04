# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: daemon sub-commands — start, stop, status, status-line."""

from __future__ import annotations

import argparse
import os
import sys

from generic_ml_cache_cli import config
from generic_ml_cache_cli.composition import store_root


def cmd_daemon(_args: argparse.Namespace) -> int:
    print("usage: gmlcache daemon {start,stop,status}", file=sys.stderr)
    return 1


def cmd_daemon_start(args: argparse.Namespace) -> int:
    try:
        from generic_ml_cache_daemon.app import create_app
    except ImportError:
        print(
            "error: generic-ml-cache-daemon is not installed. "
            "Install it with: pip install generic-ml-cache-daemon",
            file=sys.stderr,
        )
        return 1
    try:
        import uvicorn
    except ImportError:
        print("error: uvicorn is not installed (install generic-ml-cache-daemon)", file=sys.stderr)
        return 1

    store_root_path = store_root()
    if store_root_path is None:
        return 4

    session_id: str | None = getattr(args, "session", None) or None
    enable_metrics: bool = getattr(args, "metrics", False)
    host: str = args.host
    port: int = args.port

    _daemon_cfg = config.load()
    settings = config.resolve_settings(_daemon_cfg)
    max_size = config.resolved_max_size(settings)
    max_age = config.resolved_max_age(settings)

    application = create_app(
        store_root_path,
        session_id=session_id,
        enable_metrics=enable_metrics,
        max_size=max_size,
        max_age=max_age,
        whitelist=_daemon_cfg.adapters,
    )
    uvicorn.run(application, host=host, port=port)
    return 0


def cmd_daemon_status(args: argparse.Namespace) -> int:
    import json as _json
    import urllib.error
    import urllib.request

    host: str = args.host
    port: int = args.port
    url = f"http://{host}:{port}/health"  # NOSONAR — localhost daemon, plain HTTP is correct
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
        import json as _json2

        print(_json2.dumps({"status": status, "host": host, "port": port}))
    else:
        print(f"daemon: {status} (http://{host}:{port})")
    return 0 if status == "ok" else 1


def cmd_daemon_stop(args: argparse.Namespace) -> int:
    import signal
    import urllib.error
    import urllib.request

    host: str = args.host
    port: int = args.port
    health_url = f"http://{host}:{port}/health"  # NOSONAR — localhost daemon, plain HTTP is correct
    try:
        urllib.request.urlopen(health_url, timeout=3)  # noqa: S310
    except urllib.error.URLError:
        print("daemon: not running", file=sys.stderr)
        return 1

    store_root_path = store_root()
    pid_path = (store_root_path / ".daemon.pid") if store_root_path else None
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


def cmd_status_line(args: argparse.Namespace) -> int:  # NOSONAR — always 0 by design
    """Emit live session stats as JSON for status-bar integrations.

    Designed to be called repeatedly by a status-bar formatter script.  Exits 0
    and prints nothing when no session is active or the daemon is not running —
    the caller decides how to handle absence.
    """
    import urllib.request

    session_id: str | None = getattr(args, "session", None) or os.environ.get("GMLCACHE_SESSION")
    if not session_id:
        return 0

    host: str = args.host
    port: int = args.port
    stats_url = f"http://{host}:{port}/sessions/{session_id}/stats"  # NOSONAR
    try:
        with urllib.request.urlopen(stats_url, timeout=2) as response:  # noqa: S310
            print(response.read().decode())
    except OSError:
        pass
    return 0  # NOSONAR — always 0 by design: daemon absence is not an error for the status bar
