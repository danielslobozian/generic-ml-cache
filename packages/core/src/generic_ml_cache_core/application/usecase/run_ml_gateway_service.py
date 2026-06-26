# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlGatewayService — orchestrates the cache-check / forward / store / record cycle."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.gateway.forwarded_response import (
    ForwardedResponse,
)
from generic_ml_cache_core.application.domain.model.gateway.gateway_response import GatewayResponse
from generic_ml_cache_core.application.domain.model.identity.gateway_call_identity import (
    GatewayCallIdentity,
)
from generic_ml_cache_core.application.port.inbound.run_ml_gateway_command import (
    RunMlGatewayCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_gateway_use_case import (
    RunMlGatewayUseCase,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.out.gateway_forward_port import GatewayForwardPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.usecase import journal_events

_SUCCESS_STATUS = 200


class RunMlGatewayService(RunMlGatewayUseCase):
    """Implements the gateway use case: check blob store, forward on miss, cache on 200.

    Only successful (HTTP 200) upstream responses are stored and recorded.
    Error responses are forwarded verbatim without touching the store or repository.
    Both hits and misses are journalled to the metrics port so session stats reflect
    real gateway traffic.
    """

    def __init__(
        self,
        blob_store: BlobStorePort,
        gateway_forward_port: GatewayForwardPort,
        repository: ExecutionRepositoryPort,
        metrics: MetricsPort,
    ) -> None:
        self._blob_store = blob_store
        self._gateway_forward_port = gateway_forward_port
        self._repository = repository
        self._metrics = metrics

    def execute(self, command: RunMlGatewayCommand) -> GatewayResponse:
        """Return a cached response on hit, or forward and record the upstream response."""
        cached_response = self.load_cached_response(command)
        if cached_response is not None:
            return cached_response
        forwarded = self._gateway_forward_port.forward(
            command.gateway_request,
            command.api_token,
            command.target_url,
            command.forward_headers,
        )
        return self.record_forwarded_response(command, forwarded)

    def load_cached_response(self, command: RunMlGatewayCommand) -> GatewayResponse | None:
        """Return a cached response and record a hit, or None on cache miss."""
        if not command.gateway_request.is_cacheable():
            return None
        cache_key = command.gateway_request.generate_cache_key()
        cached_bytes = self._blob_store.get(cache_key)
        if cached_bytes is not None:
            self._record_hit(cache_key, command)
            return GatewayResponse(
                response_body_bytes=cached_bytes,
                status_code=_SUCCESS_STATUS,
                cache_hit=True,
            )
        return None

    def record_forwarded_response(
        self, command: RunMlGatewayCommand, forwarded: ForwardedResponse
    ) -> GatewayResponse:
        """Store and journal a forwarded response when it is successful and cacheable."""
        cache_key = command.gateway_request.generate_cache_key()
        if forwarded.status_code == _SUCCESS_STATUS:
            if command.gateway_request.is_cacheable():
                self._blob_store.put(cache_key, forwarded.body_bytes)
                self._record_miss(cache_key, command, forwarded)
        return GatewayResponse(
            response_body_bytes=forwarded.body_bytes,
            status_code=forwarded.status_code,
            cache_hit=False,
        )

    def _record_hit(self, cache_key: str, command: RunMlGatewayCommand) -> None:
        self._metrics.record_event(
            journal_events.HIT,
            execution_key=cache_key,
            client=command.gateway_request.client_name(),
            model=command.gateway_request.request_model(),
            effort="",
            session_id=command.session_id,
        )

    def _record_miss(
        self,
        cache_key: str,
        command: RunMlGatewayCommand,
        forwarded: ForwardedResponse,
    ) -> None:
        input_bytes = command.gateway_request.serialize_request()
        input_key = f"{cache_key}.req"
        self._blob_store.put(input_key, input_bytes)
        input_artifact = Artifact.from_content(
            artifact_type=ArtifactType.INPUT_MESSAGES,
            blob_key=input_key,
            content=input_bytes,
        )
        output_artifact = Artifact.from_content(
            artifact_type=ArtifactType.STDOUT,
            blob_key=cache_key,
            content=forwarded.body_bytes,
        )
        execution = MlExecution(
            call_identity=GatewayCallIdentity(cache_key=cache_key),
            execution_state=ExecutionState.SUCCESS,
            execution_kind=ExecutionKind.API,
            output_persisted=True,
            artifacts=[input_artifact, output_artifact],
            token_usage=command.gateway_request.parse_token_usage(forwarded.body_bytes),
        )
        self._repository.save(execution)
        self._metrics.record_event(
            journal_events.RECORD,
            execution_key=cache_key,
            client=command.gateway_request.client_name(),
            model=command.gateway_request.request_model(),
            effort="",
            session_id=command.session_id,
        )
