# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ApiPassthroughRunnerPort — the outbound role of a verbatim API-passthrough relay.

The API analog of :class:`PassthroughLocalRunnerPort`: a raw relay that forwards
the opaque request bytes to an operator-configured upstream endpoint and returns
the verbatim response. Unlike :class:`MlRunnerPort` (which takes a structured
``MlRequest`` and distils a text answer), this preserves the wire response exactly
— the full JSON envelope, not just its text blocks — because the caller (an HTTP
gateway) forwards it back untouched.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.run.api_passthrough_request import (
    ApiPassthroughRequest,
)
from generic_ml_cache_core.application.domain.model.run.client_answer import ClientAnswer


class ApiPassthroughRunnerPort(ABC):
    """Relay a raw provider-API request verbatim and report the wire outcome.

    The answer's ``exit_code`` carries the upstream HTTP status (0 for a 200,
    otherwise the status itself), ``stdout`` the raw response body, and
    ``token_usage`` the provider's usage — so the shared cache protocol treats a
    200 as a servable success and any other status as a non-cached failure that is
    still returned verbatim. Transport failures (DNS, timeout, TLS) are translated
    to the project's error vocabulary at the adapter boundary, never leaked raw.
    """

    @abstractmethod
    def execute_api_passthrough(self, request: ApiPassthroughRequest) -> ClientAnswer:
        """Forward the raw request bytes upstream and map the wire response to an
        answer. No workspace, no artifact capture — a raw relay."""
