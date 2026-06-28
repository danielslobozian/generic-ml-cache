# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from generic_ml_cache_core.application.port.inbound.run_ml_execution_use_case import (
    RunMlExecutionUseCase,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.usecase.probe_service import ProbeService
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.application.usecase.run_ml_gateway_service import RunMlGatewayService


@dataclass(frozen=True)
class WiredUseCases:
    """Typed container of wired use-case and port references.

    Constructed by the driver application's private composition root;
    passed to controllers to invoke the domain.
    """

    run_ml: RunMlExecutionUseCase
    probe: ProbeService
    purge: PurgeService
    blob_store: BlobStorePort
    repository: ExecutionRepositoryPort
    metrics: MetricsPort
    run_gateway: RunMlGatewayService
    diag: Optional[DiagnosticsPort] = None
