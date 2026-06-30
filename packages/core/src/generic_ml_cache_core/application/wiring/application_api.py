# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache_core.application.port.inbound.probe_use_case import ProbeUseCase
from generic_ml_cache_core.application.port.inbound.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.inbound.run_ml_gateway_use_case import (
    RunMlGatewayUseCase,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.usecase.execution_query_service import ExecutionQueryService
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.application.usecase.session_admin_service import SessionAdminService
from generic_ml_cache_core.application.usecase.session_report_service import SessionReportService
from generic_ml_cache_core.application.usecase.session_tags_service import SessionTagsService
from generic_ml_cache_core.application.usecase.store_stats_service import StoreStatsService


@dataclass(frozen=True)
class ApplicationApi:
    """Typed container of wired use-case and port references.

    Constructed by the driver application's private composition root; passed to
    controllers to invoke the domain. Use-case fields are typed against the
    inbound *ports* (``RunMlExecutionUseCase``/``ProbeUseCase``/``RunMlGatewayUseCase``)
    so controllers depend on contracts, not implementations. ``purge`` keeps its
    concrete ``PurgeService`` type: its surface is broad (per-key/tag/session
    purge, hard-delete, eviction) and no second implementation exists, so a
    mirror interface would add boilerplate without inverting any real dependency.

    This is a wiring concern, not a port — it lives outside ``application.port``
    precisely so the port ring can stay free of use-case imports.
    """

    run_ml: RunMlExecutionUseCase
    probe: ProbeUseCase
    purge: PurgeService
    session_tags: SessionTagsService
    session_admin: SessionAdminService
    session_report: SessionReportService
    execution_query: ExecutionQueryService
    store_stats: StoreStatsService
    blob_store: BlobStorePort
    repository: ExecutionRepositoryPort
    metrics: MetricsPort
    run_gateway: RunMlGatewayUseCase
    diag: DiagnosticsPort | None = None
