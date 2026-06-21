# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ProbeService."""

from __future__ import annotations

from generic_ml_cache.application.domain.model.probe.probe_report import ProbeReport
from generic_ml_cache.application.domain.model.probe.probe_status import ProbeStatus
from generic_ml_cache.application.port.inbound.probe_command import ProbeCommand
from generic_ml_cache.application.port.inbound.probe_use_case import ProbeUseCase
from generic_ml_cache.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache.application.usecase.call_identity_building import build_call_identity


class ProbeService(ProbeUseCase):
    """Forecast whether a call is cached, without running or recording anything.

    It reuses the shared key-building and cacheability rule, so the verdict and the
    key are byte-for-byte what a run would derive — a probe and a run can never
    disagree. It launches no client, writes no blob, and records no journal event.
    """

    def __init__(
        self, file_fingerprint: FileFingerprintPort, repository: ExecutionRepositoryPort
    ) -> None:
        self._file_fingerprint = file_fingerprint
        self._repository = repository

    def execute(self, command: ProbeCommand) -> ProbeReport:
        call_identity = build_call_identity(self._file_fingerprint, command)
        execution_key = call_identity.generate_key()

        if command.is_uncacheable:
            return ProbeReport(status=ProbeStatus.NON_CACHEABLE, execution_key=execution_key)

        current_execution = self._repository.find_current(execution_key)
        if current_execution is None:
            return ProbeReport(status=ProbeStatus.MISS, execution_key=execution_key)
        return ProbeReport(
            status=ProbeStatus.HIT, execution_key=execution_key, execution=current_execution
        )
