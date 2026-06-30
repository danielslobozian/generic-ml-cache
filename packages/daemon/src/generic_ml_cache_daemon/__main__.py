# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Entry point: run the daemon via ``python -m generic_ml_cache_daemon``."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import uvicorn

from generic_ml_cache_daemon.app import create_app

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765

_SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
_AGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _parse_size(raw: str) -> int | None:
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([a-z]*)", raw.strip().lower().replace(" ", ""))
    if not m:
        return None
    number, unit = m.group(1), m.group(2) or "b"
    factor = _SIZE_UNITS.get(unit)
    return int(float(number) * factor) if factor else None


def _parse_age(raw: str) -> float | None:
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([a-z]*)", raw.strip().lower().replace(" ", ""))
    if not m:
        return None
    number, unit = m.group(1), m.group(2) or "s"
    factor = _AGE_UNITS.get(unit)
    return float(number) * factor if factor else None


def _parse_adapters(raw: str) -> frozenset[str] | None:
    """Parse GMLCACHE_ADAPTERS: '*'/empty → None (all); 'claude,cursor' → frozenset."""
    text = raw.strip()
    if not text or text == "*":
        return None
    return frozenset(name.strip() for name in text.split(",") if name.strip())


def main(argv: list[str] | None = None) -> None:
    # Parse args first so ``--help`` prints usage and exits *before* any server
    # starts. All cache behaviour is configured by GMLCACHE_* environment variables;
    # the only flags are the bind host/port. ``argv`` defaults to ``sys.argv[1:]``;
    # tests pass an explicit list so the runner's own argv is never parsed here.
    parser = argparse.ArgumentParser(
        prog="python -m generic_ml_cache_daemon",
        description=(
            "Run the generic-ml-cache HTTP daemon. Cache configuration is read from "
            "GMLCACHE_* environment variables: GMLCACHE_STORE, GMLCACHE_SESSION, "
            "GMLCACHE_METRICS, GMLCACHE_MAX_SIZE, GMLCACHE_MAX_AGE, "
            "GMLCACHE_EVICTION_INTERVAL, GMLCACHE_ADAPTERS."
        ),
    )
    parser.add_argument("--host", default=_DEFAULT_HOST, help="bind host (default: %(default)s)")
    parser.add_argument(
        "--port", type=int, default=_DEFAULT_PORT, help="bind port (default: %(default)s)"
    )
    args = parser.parse_args(argv)

    store_root = Path(os.environ.get("GMLCACHE_STORE", str(Path.home() / ".gmlcache")))
    session_id = os.environ.get("GMLCACHE_SESSION") or None
    enable_metrics = os.environ.get("GMLCACHE_METRICS", "").lower() in ("1", "true", "yes")

    max_size_raw = os.environ.get("GMLCACHE_MAX_SIZE", "")
    max_size = _parse_size(max_size_raw) if max_size_raw else None

    max_age_raw = os.environ.get("GMLCACHE_MAX_AGE", "")
    max_age = _parse_age(max_age_raw) if max_age_raw else None

    interval_raw = os.environ.get("GMLCACHE_EVICTION_INTERVAL", "")
    eviction_interval = float(interval_raw) if interval_raw else 3600.0

    adapters_raw = os.environ.get("GMLCACHE_ADAPTERS", "")
    whitelist = _parse_adapters(adapters_raw) if adapters_raw else None

    application = create_app(
        store_root,
        session_id=session_id,
        enable_metrics=enable_metrics,
        max_size=max_size,
        max_age=max_age,
        eviction_interval=eviction_interval,
        whitelist=whitelist,
    )
    uvicorn.run(application, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    main()
