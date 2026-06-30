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
from generic_ml_cache_core.application.usecase.artifact_content_service import (
    ArtifactContentService,
)
from generic_ml_cache_core.application.usecase.execution_query_service import ExecutionQueryService
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.application.usecase.session_admin_service import SessionAdminService
from generic_ml_cache_core.application.usecase.session_report_service import SessionReportService
from generic_ml_cache_core.application.usecase.session_tags_service import SessionTagsService
from generic_ml_cache_core.application.usecase.store_stats_service import StoreStatsService


@dataclass(frozen=True)
class ApplicationApi:
    """The application's API surface: the bundle of inbound ports the drivers call.

    Constructed by the composition root (``bootstrap.build_application_api``) and
    passed to controllers. **Every field is an inbound port** — the run/probe/
    gateway use-case contracts and the per-capability services (purge, session
    tags/admin/report, execution query, store stats, artifact content). The
    out-ports (blob store, repository, metrics, diagnostics) are deliberately NOT
    here: the composition root injects them into the use-case impls, so a
    controller literally cannot reach an outbound adapter — "make illegal states
    unrepresentable" (§7.4). Enforced by import-linter Rule 10.

    The service-typed fields (e.g. ``purge``) keep their concrete type: each is a
    single application service implementing the capability's inbound-port ABCs,
    with no second implementation, so a mirror interface would add boilerplate
    without inverting any real dependency.

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
    artifacts: ArtifactContentService
    run_gateway: RunMlGatewayUseCase
