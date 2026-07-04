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
from generic_ml_cache_core.application.port.inbound.session_admin.execution_keys_for_session_command import (
    ExecutionKeysForSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.execution_keys_for_session_use_case import (
    ExecutionKeysForSessionUseCase,
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
from generic_ml_cache_core.application.port.inbound.session_admin.sessions_for_tag_command import (
    SessionsForTagCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.sessions_for_tag_use_case import (
    SessionsForTagUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_command import (
    SetSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_use_case import (
    SetSessionSpecUseCase,
)
from generic_ml_cache_core.application.port.outbound.call_journal_ports import (
    SessionQueryPort,
    SessionSpecPort,
)


class SessionAdminService(
    SetSessionSpecUseCase,
    ClearSessionSpecUseCase,
    GetSessionSpecUseCase,
    ListSessionIdsUseCase,
    SessionsForTagUseCase,
    ExecutionKeysForSessionUseCase,
):
    """Manage a session's execution spec and enumerate sessions."""

    def __init__(self, specs: SessionSpecPort, sessions: SessionQueryPort) -> None:
        self._specs = specs
        self._sessions = sessions

    def set_spec(self, command: SetSessionSpecCommand) -> None:
        self._specs.set_session_spec(command.session_id, command.spec)

    def clear_spec(self, command: ClearSessionSpecCommand) -> None:
        self._specs.clear_session_spec(command.session_id)

    def get_spec(self, command: GetSessionSpecCommand) -> SessionSpec | None:
        return self._specs.session_spec(command.session_id)

    def list_session_ids(self) -> list[str]:
        return self._specs.list_session_ids()

    def sessions_for_tag(self, command: SessionsForTagCommand) -> list[str]:
        return self._sessions.session_ids_for_tag(command.tag)

    def execution_keys_for_session(self, command: ExecutionKeysForSessionCommand) -> list[str]:
        return self._sessions.execution_keys_for_session(command.session_id)
