# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""generic-ml-cache: a content-addressed cache/proxy for agentic CLI calls.

Record a real ML client (or API) call once, replay it forever by its content key.

The hexagonal core lives under ``application/`` (domain model, use cases, ports);
the adapters and the CLI live under ``adapter/``. This module re-exports a small,
stable surface; the full library API (the inbound ports and commands) is imported
from ``application.port.inbound``.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("generic-ml-cache")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0+unknown"

from generic_ml_cache.adapter.out.client import (  # noqa: E402  # fmt: skip
    ClientAdapter,
    get_adapter,
    register,
)
from generic_ml_cache.common.checksum import (  # noqa: E402  # fmt: skip
    checksum_input_data,
    file_content_fingerprint,
    text_checksum,
)
from generic_ml_cache.common.errors import (  # noqa: E402  # fmt: skip
    CacheError,
    CacheMiss,
    ClientNotFound,
    RunInterrupted,
    UnknownClient,
)

__all__ = [
    "__version__",
    "register",
    "get_adapter",
    "ClientAdapter",
    "checksum_input_data",
    "text_checksum",
    "file_content_fingerprint",
    "CacheError",
    "CacheMiss",
    "ClientNotFound",
    "RunInterrupted",
    "UnknownClient",
]
