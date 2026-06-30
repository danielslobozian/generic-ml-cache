# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SessionAdminService — the session-admin capability (set / clear exec spec).

One application service implementing the capability's single-method use cases,
each a distinct method backed by its own inbound-port ABC. Delegates to the
metrics out-port, where session-spec persistence lives.
"""

from __future__ import annotations

from generic_ml_cache_core.application.port.inbound.session_admin.clear_session_spec_command import (
    ClearSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.clear_session_spec_use_case import (
    ClearSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_command import (
    SetSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_use_case import (
    SetSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


class SessionAdminService(SetSessionSpecUseCase, ClearSessionSpecUseCase):
    """Set and clear a session's execution spec via the metrics out-port."""

    def __init__(self, metrics: MetricsPort) -> None:
        self._metrics = metrics

    def set_spec(self, command: SetSessionSpecCommand) -> None:
        self._metrics.set_session_spec(command.session_id, command.spec)

    def clear_spec(self, command: ClearSessionSpecCommand) -> None:
        self._metrics.clear_session_spec(command.session_id)
