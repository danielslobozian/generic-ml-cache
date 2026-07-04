# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""RunMlGatewayService — orchestrates the cache-check / forward / store / record cycle."""

from __future__ import annotations

import time

from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.blob_key import BlobKey
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
from generic_ml_cache_core.application.port.inbound.run_ml_gateway.run_ml_gateway_command import (
    RunMlGatewayCommand,
)
from generic_ml_cache_core.application.port.inbound.run_ml_gateway.run_ml_gateway_use_case import (
    RunMlGatewayUseCase,
)
from generic_ml_cache_core.application.port.outbound.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.outbound.call_journal_ports import RecordCallEventPort
from generic_ml_cache_core.application.port.outbound.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.application.port.outbound.gateway_forward_port import GatewayForwardPort
from generic_ml_cache_core.application.port.outbound.ml_run_ports import SaveMlRunPort
from generic_ml_cache_core.common import journal_events

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
        repository: SaveMlRunPort,
        metrics: RecordCallEventPort,
        diag: DiagnosticsPort | None = None,
    ) -> None:
        self._blob_store = blob_store
        self._gateway_forward_port = gateway_forward_port
        self._repository = repository
        self._metrics = metrics
        self._diag: DiagnosticsPort | None = diag

    def execute(self, command: RunMlGatewayCommand) -> GatewayResponse:
        """Return a cached response on hit, or forward and record the upstream response."""
        _t = time.perf_counter()
        if self._diag:
            self._diag.debug("gateway execute ENTER", session=command.session_id)
        cached_response = self.load_cached_response(command)
        if cached_response is not None:
            if self._diag:
                self._diag.debug(
                    "gateway execute EXIT",
                    duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                    cache_hit=True,
                )
            return cached_response
        forwarded = self._gateway_forward_port.forward(
            command.gateway_request,
            command.api_token,
            command.target_url,
            command.forward_headers,
        )
        result = self.record_forwarded_response(command, forwarded)
        if self._diag:
            self._diag.debug(
                "gateway execute EXIT",
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                cache_hit=False,
            )
        return result

    def load_cached_response(self, command: RunMlGatewayCommand) -> GatewayResponse | None:
        """Return a cached response and record a hit, or None on cache miss."""
        _t = time.perf_counter()
        if not command.gateway_request.is_cacheable():
            return None
        cache_key = command.gateway_request.generate_cache_key()
        if self._diag:
            self._diag.debug("load-cached-response ENTER", key=cache_key)
        cached_bytes = self._blob_store.get(cache_key)
        if cached_bytes is not None:
            if self._diag:
                self._diag.debug("gateway HIT", key=cache_key)
            self._record_hit(cache_key, command)
            if self._diag:
                self._diag.debug(
                    "load-cached-response EXIT",
                    key=cache_key,
                    duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                    hit=True,
                )
            return GatewayResponse(
                response_body_bytes=cached_bytes,
                status_code=_SUCCESS_STATUS,
                cache_hit=True,
            )
        if self._diag:
            self._diag.debug(
                "load-cached-response EXIT",
                key=cache_key,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                hit=False,
            )
        return None

    def record_forwarded_response(
        self, command: RunMlGatewayCommand, forwarded: ForwardedResponse
    ) -> GatewayResponse:
        """Store and journal a forwarded response when it is successful and cacheable."""
        _t = time.perf_counter()
        cache_key = command.gateway_request.generate_cache_key()
        if self._diag:
            self._diag.debug(
                "record-forwarded-response ENTER", key=cache_key, status=forwarded.status_code
            )
        if forwarded.status_code == _SUCCESS_STATUS:
            if command.gateway_request.is_cacheable():
                if self._diag:
                    self._diag.info(
                        "gateway MISS — forwarded and cached",
                        key=cache_key,
                        duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                    )
                self._record_miss(cache_key, command, forwarded)
        else:
            if self._diag:
                self._diag.warn(
                    "gateway upstream error — response not cached",
                    status=forwarded.status_code,
                    key=cache_key,
                    duration_ms=round((time.perf_counter() - _t) * 1000, 1),
                )
        if self._diag:
            self._diag.debug(
                "record-forwarded-response EXIT",
                key=cache_key,
                duration_ms=round((time.perf_counter() - _t) * 1000, 1),
            )
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
        input_key = BlobKey(f"{cache_key}.req")
        output_key = BlobKey(cache_key)
        input_artifact = Artifact.from_content(
            artifact_type=ArtifactType.INPUT_MESSAGES,
            blob_key=input_key,
            content=input_bytes,
            status=ArtifactStatus.PENDING,
        )
        output_artifact = Artifact.from_content(
            artifact_type=ArtifactType.STDOUT,
            blob_key=output_key,
            content=forwarded.body_bytes,
            status=ArtifactStatus.PENDING,
        )
        # DB-first: save the rows PENDING (not yet servable) before writing any blob,
        # so a failed blob write can never orphan bytes; finalize only when both land.
        execution = MlExecution(
            call_identity=GatewayCallIdentity(cache_key=cache_key),
            execution_state=ExecutionState.SUCCESS,
            execution_kind=ExecutionKind.API,
            output_persisted=False,
            artifacts=[input_artifact, output_artifact],
            token_usage=command.gateway_request.parse_token_usage(forwarded.body_bytes),
        )
        self._repository.save(execution)
        all_stored = True
        for blob_key, content in ((input_key, input_bytes), (output_key, forwarded.body_bytes)):
            try:
                self._blob_store.put(blob_key, content)
                self._repository.mark_artifacts_stored(cache_key, blob_key)
            except Exception as exc:  # noqa: BLE001 — surface any blob-write failure as FAILED (§10)
                self._repository.mark_artifacts_failed(cache_key, blob_key, str(exc))
                all_stored = False
                if self._diag:
                    self._diag.error(
                        "gateway blob write failed", key=cache_key, blob=blob_key, exc=exc
                    )
        if all_stored:
            self._repository.finalize_output_persisted(cache_key)
        self._metrics.record_event(
            journal_events.RECORD,
            execution_key=cache_key,
            client=command.gateway_request.client_name(),
            model=command.gateway_request.request_model(),
            effort="",
            session_id=command.session_id,
        )
