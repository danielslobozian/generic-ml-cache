# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""generic-ml-cache: a content-addressed cache/proxy for agentic CLI calls.

Record a real call once, replay it forever by checksum.

Public API (stable surface for v0.x):
    Request, Mode, resolve, apply_response  -- the cache core
    Cassette, CapturedFile, Response        -- the cassette format
    CassetteStore                           -- the on-disk store
    register, get_adapter, ClientAdapter    -- the adapter seam
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("generic-ml-cache")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0+unknown"

from .adapters import ClientAdapter, get_adapter, register  # noqa: E402  # fmt: skip
from .cache import Mode, Outcome, Request, apply_response, resolve  # noqa: E402  # fmt: skip
from .cassette import CapturedFile, Cassette, Response  # noqa: E402  # fmt: skip
from .common.checksum import checksum_input_data, text_checksum  # noqa: E402  # fmt: skip
from .common.errors import (  # noqa: E402  # fmt: skip
    CacheError,
    CacheMiss,
    CassetteFormatError,
    ClientNotFound,
    RunInterrupted,
    UnknownClient,
)
from .store import CassetteStore  # noqa: E402  # fmt: skip

__all__ = [
    "__version__",
    "Request",
    "Mode",
    "Outcome",
    "resolve",
    "apply_response",
    "Cassette",
    "CapturedFile",
    "Response",
    "CassetteStore",
    "register",
    "get_adapter",
    "ClientAdapter",
    "checksum_input_data",
    "text_checksum",
    "CacheError",
    "CacheMiss",
    "CassetteFormatError",
    "ClientNotFound",
    "RunInterrupted",
    "UnknownClient",
]
