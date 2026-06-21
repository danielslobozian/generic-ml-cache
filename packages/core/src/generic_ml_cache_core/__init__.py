# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""generic-ml-cache-core: the hexagonal core library.

Record a real ML client (or API) call once, replay it forever by its content key.

This is a stateless library: it holds the domain model, the use cases, the port
contracts, AND the default outbound adapters (SQLite execution repository,
filesystem blob store, local client runner, API client, metrics, clock,
fingerprint). It bakes in *structure* (table names, blob naming, schema) but no
*location* -- the data source (store path) and configuration are injected by the
caller. Wire it with :func:`build_use_cases`, or construct the adapters and use
cases directly. The CLI / a daemon / an embedding app are inbound drivers that
supply the data source and map their surface onto this library.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("generic-ml-cache-core")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0+unknown"

from generic_ml_cache_core.adapter.inbound.composition import (  # noqa: E402  # fmt: skip
    WiredUseCases,
    build_use_cases,
)
from generic_ml_cache_core.adapter.out.client import (  # noqa: E402  # fmt: skip
    ClientAdapter,
    get_adapter,
    register,
)
from generic_ml_cache_core.common.checksum import (  # noqa: E402  # fmt: skip
    checksum_input_data,
    file_content_fingerprint,
    text_checksum,
)
from generic_ml_cache_core.common.errors import (  # noqa: E402  # fmt: skip
    CacheError,
    CacheMiss,
    ClientNotFound,
    RunInterrupted,
    UnknownClient,
)

__all__ = [
    "__version__",
    "build_use_cases",
    "WiredUseCases",
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
