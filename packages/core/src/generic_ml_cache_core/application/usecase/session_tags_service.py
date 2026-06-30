# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SessionTagsService — the session-tags capability.

One application service implementing the capability's single-method use cases
(School B "regroup by type"): tag, untag, list. Each operation is a distinct
method backed by its own inbound-port ABC; the service owns no policy beyond
delegating to the metrics out-port, where session-tag persistence lives.
"""

from __future__ import annotations

from generic_ml_cache_core.application.port.inbound.session_tags.list_session_tags_command import (
    ListSessionTagsCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.list_session_tags_use_case import (
    ListSessionTagsUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_tags.tag_session_command import (
    TagSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.tag_session_use_case import (
    TagSessionUseCase,
)
from generic_ml_cache_core.application.port.inbound.session_tags.untag_session_command import (
    UntagSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.untag_session_use_case import (
    UntagSessionUseCase,
)
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort


class SessionTagsService(TagSessionUseCase, UntagSessionUseCase, ListSessionTagsUseCase):
    """Tag, untag, and list a session's tags via the metrics out-port."""

    def __init__(self, metrics: MetricsPort) -> None:
        self._metrics = metrics

    def tag(self, command: TagSessionCommand) -> None:
        self._metrics.add_session_tag(command.session_id, command.tag)

    def untag(self, command: UntagSessionCommand) -> None:
        self._metrics.remove_session_tag(command.session_id, command.tag)

    def list_tags(self, command: ListSessionTagsCommand) -> list[str]:
        return self._metrics.session_tags(command.session_id)
