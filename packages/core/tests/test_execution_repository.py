# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ExecutionRepositoryPort and the in-memory adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from generic_ml_cache_core.adapter.out.persistence.in_memory_execution_repository import (
    InMemoryExecutionRepository,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact, ArtifactType
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)

_FIXED_MOMENT = datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FixedClock(ClockPort):
    def __init__(self, moment: datetime = _FIXED_MOMENT) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _identity(prompt_fingerprint: str = "prompt_sha") -> ManagedCallIdentity:
    return ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="ctx_sha",
        prompt_fingerprint=prompt_fingerprint,
    )


def _execution(
    identity: ManagedCallIdentity,
    state: ExecutionState = ExecutionState.SUCCESS,
    output_persisted: bool = True,
    content: bytes = b"answer",
    tags=None,
) -> MlExecution:
    artifact = Artifact(
        artifact_type=ArtifactType.STDOUT,
        blob_key="blob_" + content.hex(),
        size_bytes=len(content),
        content=content,
    )
    failure = (
        ExecutionFailure(reason=FailureReason.NONZERO_EXIT, message="boom", exit_code=1)
        if state is ExecutionState.FAILED
        else None
    )
    return MlExecution(
        call_identity=identity,
        execution_state=state,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=output_persisted,
        artifacts=[artifact],
        failure=failure,
        tags=tags or [],
    )


def _repository() -> InMemoryExecutionRepository:
    return InMemoryExecutionRepository(clock=FixedClock())


# --- contract ----------------------------------------------------------------


def test_port_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ExecutionRepositoryPort()  # type: ignore[abstract]


def test_in_memory_adapter_is_an_execution_repository_port():
    assert isinstance(_repository(), ExecutionRepositoryPort)


# --- find_current ------------------------------------------------------------


def test_find_current_is_none_for_unknown_key():
    assert _repository().find_current("nope") is None


def test_save_then_find_current_returns_the_execution():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity))
    found = repository.find_current(identity.generate_key())
    assert found is not None
    assert found.execution_state is ExecutionState.SUCCESS


def test_tags_are_carried_through_save_and_find():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity, tags=["id-scan", "ticket"]))
    found = repository.find_current(identity.generate_key())
    assert found.tags == ["id-scan", "ticket"]


def test_find_current_returns_dehydrated_artifacts():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity, content=b"answer"))
    found = repository.find_current(identity.generate_key())
    artifact = found.artifacts[0]
    assert artifact.content is None  # the repository holds no bytes
    assert artifact.blob_key == "blob_" + b"answer".hex()  # the reference survives


def test_failed_execution_is_not_current():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity, state=ExecutionState.FAILED, output_persisted=False))
    assert repository.find_current(identity.generate_key()) is None


def test_unpersisted_success_is_not_current():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity, output_persisted=False))
    assert repository.find_current(identity.generate_key()) is None


# --- supersession (refresh) --------------------------------------------------


def test_a_second_success_supersedes_the_first():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity, content=b"old"))
    repository.save(_execution(identity, content=b"new"))

    current = repository.find_current(identity.generate_key())
    assert current.artifacts[0].blob_key == "blob_" + b"new".hex()

    history = repository.find_all(identity.generate_key())
    assert len(history) == 2
    assert history[0].superseded_at == _FIXED_MOMENT  # old one stamped stale
    assert history[1].superseded_at is None  # new one is current


def test_failed_refresh_does_not_supersede_the_current():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity, content=b"good"))
    repository.save(_execution(identity, state=ExecutionState.FAILED, output_persisted=False))

    current = repository.find_current(identity.generate_key())
    assert current is not None
    assert current.artifacts[0].blob_key == "blob_" + b"good".hex()
    history = repository.find_all(identity.generate_key())
    assert history[0].superseded_at is None  # the good one is still current


def test_unpersisted_success_refresh_does_not_supersede_the_current():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity, content=b"good"))
    repository.save(_execution(identity, output_persisted=False, content=b"ghost"))

    current = repository.find_current(identity.generate_key())
    assert current.artifacts[0].blob_key == "blob_" + b"good".hex()


def test_supersession_is_stamped_with_the_injected_clock():
    stamped_moment = datetime(2030, 1, 1, 0, 0, tzinfo=timezone.utc)
    repository = InMemoryExecutionRepository(clock=FixedClock(stamped_moment))
    identity = _identity()
    repository.save(_execution(identity, content=b"old"))
    repository.save(_execution(identity, content=b"new"))
    history = repository.find_all(identity.generate_key())
    assert history[0].superseded_at == stamped_moment


# --- append-only history -----------------------------------------------------


def test_find_all_is_empty_for_unknown_key():
    assert _repository().find_all("nope") == []


def test_find_all_counts_every_real_client_call():
    repository = _repository()
    identity = _identity()
    repository.save(_execution(identity, content=b"a"))
    repository.save(_execution(identity, content=b"b"))
    repository.save(_execution(identity, content=b"c"))
    assert len(repository.find_all(identity.generate_key())) == 3


def test_different_identities_are_isolated():
    repository = _repository()
    first = _identity("first")
    second = _identity("second")
    repository.save(_execution(first, content=b"one"))
    repository.save(_execution(second, content=b"two"))
    assert (
        repository.find_current(first.generate_key()).artifacts[0].blob_key
        == "blob_" + b"one".hex()
    )
    assert (
        repository.find_current(second.generate_key()).artifacts[0].blob_key
        == "blob_" + b"two".hex()
    )
    assert len(repository.find_all(first.generate_key())) == 1


def test_saved_execution_is_not_mutated_by_the_repository():
    repository = _repository()
    identity = _identity()
    original = _execution(identity, content=b"keepme")
    repository.save(original)
    # The caller's object keeps its bytes; only the stored copy is dehydrated.
    assert original.artifacts[0].content == b"keepme"
