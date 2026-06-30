# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for SessionTagsService (the session-tags inbound capability)."""

from generic_ml_cache_core.application.port.inbound.session_tags.list_session_tags_command import (
    ListSessionTagsCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.tag_session_command import (
    TagSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.untag_session_command import (
    UntagSessionCommand,
)
from generic_ml_cache_core.application.usecase.session_tags_service import SessionTagsService


class _FakeMetrics:
    """A duck-typed stand-in for the slice of MetricsPort the service uses."""

    def __init__(self) -> None:
        self._tags: dict[str, set[str]] = {}

    def add_session_tag(self, session_id: str, tag: str) -> None:
        self._tags.setdefault(session_id, set()).add(tag)

    def remove_session_tag(self, session_id: str, tag: str) -> None:
        self._tags.get(session_id, set()).discard(tag)

    def session_tags(self, session_id: str) -> list[str]:
        return sorted(self._tags.get(session_id, set()))


def _service() -> SessionTagsService:
    return SessionTagsService(_FakeMetrics())  # type: ignore[arg-type]  # duck-typed metrics


def test_tag_then_list():
    svc = _service()
    svc.tag(TagSessionCommand("s1", "alpha"))
    svc.tag(TagSessionCommand("s1", "beta"))
    assert svc.list_tags(ListSessionTagsCommand("s1")) == ["alpha", "beta"]


def test_untag_removes_one_tag():
    svc = _service()
    svc.tag(TagSessionCommand("s1", "alpha"))
    svc.tag(TagSessionCommand("s1", "beta"))
    svc.untag(UntagSessionCommand("s1", "alpha"))
    assert svc.list_tags(ListSessionTagsCommand("s1")) == ["beta"]


def test_list_unknown_session_is_empty():
    assert _service().list_tags(ListSessionTagsCommand("nope")) == []
