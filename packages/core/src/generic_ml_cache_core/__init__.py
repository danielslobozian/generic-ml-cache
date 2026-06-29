# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""generic-ml-cache-core: the hexagonal core library.

Record a real ML client (or API) call once, replay it forever by its content key.

This is a stateless library: it holds the domain model, the use cases, the port
contracts, AND the default outbound adapters (execution repository,
filesystem blob store, local client runner, API client, metrics, clock,
fingerprint). It bakes in *structure* (table names, blob naming, schema) but no
*location* -- the data source (store path) and configuration are injected by the
caller. Wire it using a driver application's private composition root or construct the adapters and use
cases directly. The CLI / a daemon / an embedding app are inbound drivers that
supply the data source and map their surface onto this library.

**Stability contract (from 1.0.0 onwards):**

The symbols listed in ``__all__`` (see below) are the public, stable API surface.
Under SemVer:

- **Patch releases (1.x.Y)** — no breaking changes, no new symbols required by
  callers.
- **Minor releases (1.X.0)** — backwards-compatible additions only; existing call
  sites continue to work without changes.
- **Major releases (2.0.0)** — may remove or rename public symbols; a migration
  guide will be published with the release.

Anything *not* listed in ``__all__`` — including all sub-modules under
``adapter/``, ``application/``, ``common/``, and ``migrations/`` — is internal.
Internal paths may change in any release, including patch releases.

**Public API (``__all__``):**

- :class:`WiredUseCases` — typed container of wired use-case references
- :class:`RunMlExecutionCommand` — inbound command value object
- :class:`MlRunnerPort` — outbound runner contract
- :func:`register` / :func:`get_adapter` — adapter registry
- Error hierarchy rooted at :class:`CacheError`
- Checksum utilities: :func:`checksum_input_data`, :func:`text_checksum`,
  :func:`file_content_fingerprint`
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("generic-ml-cache-core")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0+unknown"

from generic_ml_cache_core.application.port.inbound.wired_use_cases import (  # noqa: E402  # fmt: skip
    WiredUseCases,
)
from generic_ml_cache_core.adapter.registry import (  # noqa: E402  # fmt: skip
    get_adapter,
    register,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (  # noqa: E402  # fmt: skip
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.out.ml_runner_port import MlRunnerPort  # noqa: E402  # fmt: skip
from generic_ml_cache_core.common.checksum import (  # noqa: E402  # fmt: skip
    checksum_input_data,
    file_content_fingerprint,
    text_checksum,
)
from generic_ml_cache_core.common.errors import (  # noqa: E402  # fmt: skip
    ArtifactBlobMissing,
    CacheError,
    CacheMiss,
    ClientNotFound,
    CommandLineTooLong,
    ConfigError,
    EncryptionStateError,
    EncryptionTokenRequired,
    InputFileError,
    RunInterrupted,
    StoreLocked,
    UnknownClient,
    WrongEncryptionToken,
)

__all__ = [
    "__version__",
    # Composition root
    "WiredUseCases",
    # Inbound port
    "RunMlExecutionCommand",
    # Outbound port contracts
    "MlRunnerPort",
    # Adapter registry
    "register",
    "get_adapter",
    # Checksum utilities
    "checksum_input_data",
    "text_checksum",
    "file_content_fingerprint",
    # Error hierarchy
    "CacheError",
    "CacheMiss",
    "UnknownClient",
    "ConfigError",
    "ClientNotFound",
    "CommandLineTooLong",
    "InputFileError",
    "ArtifactBlobMissing",
    "WrongEncryptionToken",
    "EncryptionTokenRequired",
    "EncryptionStateError",
    "StoreLocked",
    "RunInterrupted",
]
