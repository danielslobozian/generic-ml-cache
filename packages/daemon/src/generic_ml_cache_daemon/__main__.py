# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Entry point: run the daemon via ``python -m generic_ml_cache_daemon``."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

import uvicorn

from generic_ml_cache_daemon.app import create_app

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765

_SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
_AGE_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _parse_size(raw: str) -> Optional[int]:
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)([a-z]*)", raw.strip().lower().replace(" ", ""))
    if not m:
        return None
    number, unit = m.group(1), m.group(2) or "b"
    factor = _SIZE_UNITS.get(unit)
    return int(float(number) * factor) if factor else None


def _parse_age(raw: str) -> Optional[float]:
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)([a-z]*)", raw.strip().lower().replace(" ", ""))
    if not m:
        return None
    number, unit = m.group(1), m.group(2) or "s"
    factor = _AGE_UNITS.get(unit)
    return float(number) * factor if factor else None


def main() -> None:
    store_root = Path(os.environ.get("GMLCACHE_STORE", str(Path.home() / ".gmlcache")))
    session_id = os.environ.get("GMLCACHE_SESSION") or None
    enable_metrics = os.environ.get("GMLCACHE_METRICS", "").lower() in ("1", "true", "yes")

    max_size_raw = os.environ.get("GMLCACHE_MAX_SIZE", "")
    max_size = _parse_size(max_size_raw) if max_size_raw else None

    max_age_raw = os.environ.get("GMLCACHE_MAX_AGE", "")
    max_age = _parse_age(max_age_raw) if max_age_raw else None

    application = create_app(
        store_root,
        session_id=session_id,
        enable_metrics=enable_metrics,
        max_size=max_size,
        max_age=max_age,
    )
    uvicorn.run(application, host=_DEFAULT_HOST, port=_DEFAULT_PORT)


if __name__ == "__main__":
    main()
