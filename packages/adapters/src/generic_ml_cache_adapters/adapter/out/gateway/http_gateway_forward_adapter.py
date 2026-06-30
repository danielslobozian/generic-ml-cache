# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""HttpGatewayForwardAdapter: forwards a gateway request to the real upstream endpoint."""

from __future__ import annotations

import urllib.error
import urllib.request

from generic_ml_cache_core.application.domain.model.gateway.forwarded_response import (
    ForwardedResponse,
)
from generic_ml_cache_core.application.domain.model.gateway.gateway_request import (
    GatewayRequest,
)
from generic_ml_cache_core.application.port.out.gateway_forward_port import GatewayForwardPort


class HttpGatewayForwardAdapter(GatewayForwardPort):
    """Forwards a gateway request to the upstream endpoint using stdlib urllib.

    Error responses (non-2xx) are captured and returned as ForwardedResponse
    rather than raised, so the calling route can forward them verbatim to the
    client.
    """

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout

    def forward(
        self,
        gateway_request: GatewayRequest,
        api_token: str,
        target_url: str,
        forward_headers: dict,
    ) -> ForwardedResponse:
        """POST the gateway request to ``target_url`` and return the raw response."""
        request_body = gateway_request.serialize_request()
        upstream_headers = self._build_headers(api_token, forward_headers)
        http_request = urllib.request.Request(  # noqa: S310 (operator-configured upstream, https)
            target_url,
            data=request_body,
            headers=upstream_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self._timeout) as response:  # noqa: S310 (operator-configured upstream, https)
                response_bytes = response.read()
            return ForwardedResponse(body_bytes=response_bytes, status_code=200)
        except urllib.error.HTTPError as http_error:
            error_body_bytes = http_error.read()
            return ForwardedResponse(body_bytes=error_body_bytes, status_code=http_error.code)

    def _build_headers(self, api_token: str, forward_headers: dict) -> dict:
        _skip = {"host", "connection", "content-length", "accept-encoding", "transfer-encoding"}
        upstream_headers = {k: v for k, v in forward_headers.items() if k not in _skip}
        upstream_headers["content-type"] = "application/json"
        if not upstream_headers.get("authorization") and api_token:
            upstream_headers["x-api-key"] = api_token
        return upstream_headers
