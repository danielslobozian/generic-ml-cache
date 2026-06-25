# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Entry point: run the daemon via ``python -m generic_ml_cache_daemon``."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from generic_ml_cache_daemon.app import create_app

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8765


def main() -> None:
    store_root = Path(os.environ.get("GMLCACHE_STORE", str(Path.home() / ".gmlcache")))
    session_id = os.environ.get("GMLCACHE_SESSION") or None
    enable_metrics = os.environ.get("GMLCACHE_METRICS", "").lower() in ("1", "true", "yes")
    application = create_app(store_root, session_id=session_id, enable_metrics=enable_metrics)
    uvicorn.run(application, host=_DEFAULT_HOST, port=_DEFAULT_PORT)


if __name__ == "__main__":
    main()
