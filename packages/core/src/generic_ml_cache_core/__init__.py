# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""generic-ml-cache-core: the hexagonal core library.

Record a real ML client (or API) call once, replay it forever by its content key.

This is a stateless library: it holds the domain model, the use cases, and the
port contracts — the hexagonal core, and nothing more. The outbound adapters that
implement those ports (execution repository, filesystem blob store, local CLI and
API clients, metrics, clock, fingerprint) live in the separate
``generic-ml-cache-adapters`` package; adapter discovery lives there too, behind
:class:`AdapterCatalogPort`. Core bakes in *structure* (table names, blob naming,
schema) but no *location* -- the data source (store path) and configuration are
injected by the caller. Wire it from a driver application's private composition
root, assembling the adapters from ``generic-ml-cache-adapters``. The CLI / a
daemon / an embedding app are inbound drivers that supply the data source and map
their surface onto this library.

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
``application/``, ``common/``, and ``migrations/`` — is internal.
Internal paths may change in any release, including patch releases.

**Public API (``__all__``):**

- :class:`ApplicationApi` — the bundle of inbound-port fields the drivers call
- :class:`RunMlExecutionCommand` — the inbound command value object
- **Outbound ports an embedder implements to run on their own infrastructure**
  (V33 groups the DB-backed ones into a ``PersistenceBackend`` at the bootstrap
  composition root): the ML-run store ports (:class:`SaveMlRunPort`,
  :class:`ReadMlRunPort`, :class:`AnnotateMlRunPort`, :class:`InspectMlRunsPort`,
  :class:`PurgeMlRunsPort`, :class:`RepairMlRunsPort`); the call-journal ports
  (:class:`RecordCallEventPort`, :class:`CallStatsPort`,
  :class:`SessionReportSourcePort`, :class:`SessionQueryPort`,
  :class:`PurgeJournalPort`, :class:`SessionTagsPort`, :class:`SessionSpecPort`);
  :class:`StoreMigrationPort` (+ :data:`CURRENT_MODEL_VERSION`);
  :class:`BlobStorePort`; :class:`MlRunnerPort`; :class:`AdapterCatalogPort`; and
  their DTOs (:class:`ExecutionSummary`, :class:`ExecutionSizeEntry`,
  :class:`UnpersistedRun`, :class:`SessionEventRow`).
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

# Domain vocabulary the public outbound ports reference — an embedder implementing
# a port (e.g. SaveMlRunPort) must be able to construct/read these from the stable
# surface, so they are exported alongside the ports (W21). Reached transitively:
# MlExecution exposes Artifact/TokenUsage/ExecutionState/ExecutionFailure/…; the
# annotation-walking test in test_public_api enforces the closure stays complete.
from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import (  # noqa: E402  # fmt: skip
    AdapterBoundary,
)
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (  # noqa: E402  # fmt: skip
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (  # noqa: E402  # fmt: skip
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import (  # noqa: E402  # fmt: skip
    Artifact,
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.blob_key import (  # noqa: E402  # fmt: skip
    BlobKey,
)
from generic_ml_cache_core.application.domain.model.execution.execution_failure import (  # noqa: E402  # fmt: skip
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache_core.application.domain.model.execution.execution_id import (  # noqa: E402  # fmt: skip
    ExecutionId,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import (  # noqa: E402  # fmt: skip
    ExecutionKind,
)
from generic_ml_cache_core.application.domain.model.execution.execution_state import (  # noqa: E402  # fmt: skip
    ExecutionState,
)
from generic_ml_cache_core.application.domain.model.execution.ml_execution import (  # noqa: E402  # fmt: skip
    MlExecution,
)
from generic_ml_cache_core.application.domain.model.identity.call_identity import (  # noqa: E402  # fmt: skip
    CallIdentity,
)
from generic_ml_cache_core.application.domain.model.run.client_run_result import (  # noqa: E402  # fmt: skip
    ClientRunResult,
    GeneratedFile,
)
from generic_ml_cache_core.application.domain.model.run.ml_request import (  # noqa: E402  # fmt: skip
    MlRequest,
)
from generic_ml_cache_core.application.domain.model.session.session_event_row import (  # noqa: E402  # fmt: skip
    SessionEventRow,
)
from generic_ml_cache_core.application.domain.model.session.session_spec import (  # noqa: E402  # fmt: skip
    SessionSpec,
)
from generic_ml_cache_core.application.domain.model.usage.token_usage import (  # noqa: E402  # fmt: skip
    TokenUsage,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (  # noqa: E402  # fmt: skip
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.outbound.adapter_catalog_port import (  # noqa: E402  # fmt: skip
    AdapterCatalogPort,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import (  # noqa: E402  # fmt: skip
    BlobStorePort,
)
from generic_ml_cache_core.application.port.outbound.call_journal_ports import (  # noqa: E402  # fmt: skip
    CallStatsPort,
    PurgeJournalPort,
    RecordCallEventPort,
    SessionQueryPort,
    SessionReportSourcePort,
    SessionSpecPort,
    SessionTagsPort,
)
from generic_ml_cache_core.application.port.outbound.ml_run_ports import (  # noqa: E402  # fmt: skip
    AnnotateMlRunPort,
    ExecutionSizeEntry,
    ExecutionSummary,
    InspectMlRunsPort,
    PurgeMlRunsPort,
    ReadMlRunPort,
    SaveMlRunPort,
)
from generic_ml_cache_core.application.port.outbound.ml_runner_port import (
    MlRunnerPort,  # noqa: E402  # fmt: skip
)
from generic_ml_cache_core.application.port.outbound.repair_ml_runs_port import (  # noqa: E402  # fmt: skip
    RepairMlRunsPort,
    UnpersistedRun,
)
from generic_ml_cache_core.application.port.outbound.store_migration_port import (  # noqa: E402  # fmt: skip
    CURRENT_MODEL_VERSION,
    StoreMigrationPort,
)
from generic_ml_cache_core.application.wiring.application_api import (  # noqa: E402  # fmt: skip
    ApplicationApi,
)
from generic_ml_cache_core.common.checksum import (  # noqa: E402  # fmt: skip
    checksum_input_data,
    file_content_fingerprint,
    text_checksum,
)
from generic_ml_cache_core.common.errors import (  # noqa: E402  # fmt: skip
    ArtifactBlobMissing,
    CacheError,
    CacheMiss,
    CapabilityUnavailable,
    ClientNotFound,
    CommandLineTooLong,
    ConfigError,
    EncryptionStateError,
    EncryptionTokenRequired,
    InputFileError,
    MigrationFailed,
    PersistenceContractOutdated,
    ProviderApiError,
    ProviderProtocolError,
    RunInterrupted,
    StoreConsistencyError,
    StoreCorrupt,
    StoreLocked,
    StoreUnavailable,
    UnknownClient,
    UnsupportedExecutionMode,
    WrongEncryptionToken,
)

__all__ = [
    "__version__",
    # Composition root
    "ApplicationApi",
    # Inbound port
    "RunMlExecutionCommand",
    # Outbound persistence ports — an embedder implements these to run on their own
    # store (V33 groups the DB-backed ones into a PersistenceBackend at composition).
    "SaveMlRunPort",
    "ReadMlRunPort",
    "AnnotateMlRunPort",
    "InspectMlRunsPort",
    "PurgeMlRunsPort",
    "RepairMlRunsPort",
    "ExecutionSummary",
    "ExecutionSizeEntry",
    "UnpersistedRun",
    # Outbound call-journal ports (+ its row DTO)
    "RecordCallEventPort",
    "CallStatsPort",
    "SessionReportSourcePort",
    "SessionQueryPort",
    "PurgeJournalPort",
    "SessionTagsPort",
    "SessionSpecPort",
    "SessionEventRow",
    # Outbound migration / blob / runner / catalog ports
    "StoreMigrationPort",
    "CURRENT_MODEL_VERSION",
    "BlobStorePort",
    "MlRunnerPort",
    "AdapterCatalogPort",
    # Domain vocabulary the public ports reference — the DTOs/enums an embedder
    # must construct/read to implement a port (W21). CallIdentity is exported OPAQUE
    # (its four subclasses stay internal); round-trip it with the serialize pair.
    "MlExecution",
    "Artifact",
    "ArtifactType",
    "ArtifactStatus",
    "BlobKey",
    "ExecutionId",
    "ExecutionState",
    "ExecutionKind",
    "ExecutionFailure",
    "FailureReason",
    "TokenUsage",
    "MlRequest",
    "ClientRunResult",
    "GeneratedFile",
    "AdapterDescriptor",
    "AdapterBoundary",
    "ClientCapability",
    "SessionSpec",
    "CallIdentity",
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
    # Structured errors consumers branch on (they carry a `code`/`status_code` the
    # drivers map to an exit code / HTTP status) — W22.
    "ProviderApiError",
    "ProviderProtocolError",
    "MigrationFailed",
    "UnsupportedExecutionMode",
    "CapabilityUnavailable",
    "PersistenceContractOutdated",
    "StoreUnavailable",
    "StoreCorrupt",
    "StoreConsistencyError",
]
