# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SessionAdminService — the session-admin capability.

set / clear / read a session's execution spec, and list known session ids. Each
operation is a distinct method backed by its own inbound-port ABC; the service
delegates to the metrics out-port, where session state lives.
"""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.port.inbound.session_admin.clear_session_spec_command import (
    ClearSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.clear_session_spec_use_case import (
    ClearSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.get_session_spec_command import (
    GetSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.get_session_spec_use_case import (
    GetSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.list_session_ids_use_case import (
    ListSessionIdsUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_command import (
    SetSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_use_case import (
    SetSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


class SessionAdminService(
    SetSessionSpecUseCase,
    ClearSessionSpecUseCase,
    GetSessionSpecUseCase,
    ListSessionIdsUseCase,
):
    """Manage a session's execution spec and enumerate sessions."""

    def __init__(self, metrics: MetricsPort) -> None:
        self._metrics = metrics

    def set_spec(self, command: SetSessionSpecCommand) -> None:
        self._metrics.set_session_spec(command.session_id, command.spec)

    def clear_spec(self, command: ClearSessionSpecCommand) -> None:
        self._metrics.clear_session_spec(command.session_id)

    def get_spec(self, command: GetSessionSpecCommand) -> SessionSpec | None:
        return self._metrics.session_spec(command.session_id)

    def list_session_ids(self) -> list[str]:
        return self._metrics.list_session_ids()
