# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for SqliteExecutionRepository."""

from __future__ import annotations

from datetime import datetime, timezone


from generic_ml_cache_core.adapter.out.persistence.sqlite_execution_repository import (
    SqliteExecutionRepository,
)
from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import Artifact, ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.out.clock_port import ClockPort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)

_MOMENT = datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return _MOMENT


def _repository(tmp_path) -> SqliteExecutionRepository:
    return SqliteExecutionRepository(tmp_path / "executions.sqlite3", clock=FixedClock())


def _managed_identity(prompt_fingerprint: str = "p") -> ManagedCallIdentity:
    return ManagedCallIdentity(
        client="claude",
        model="sonnet",
        effort="high",
        context_fingerprint="c",
        prompt_fingerprint=prompt_fingerprint,
    )


def _execution(
    identity,
    *,
    kind: ExecutionKind = ExecutionKind.LOCAL_MANAGED,
    state: ExecutionState = ExecutionState.SUCCESS,
    output_persisted: bool = True,
    content: bytes = b"answer",
    token_usage=None,
    failure=None,
) -> MlExecution:
    artifact = Artifact(
        artifact_type=ArtifactType.STDOUT,
        blob_key="blob_" + content.hex(),
        size_bytes=len(content),
        content=content,
    )
    return MlExecution(
        call_identity=identity,
        execution_state=state,
        execution_kind=kind,
        output_persisted=output_persisted,
        artifacts=[artifact],
        token_usage=token_usage,
        failure=failure,
    )


# --- contract ----------------------------------------------------------------


def test_is_an_execution_repository_port(tmp_path):
    assert isinstance(_repository(tmp_path), ExecutionRepositoryPort)


def test_find_current_is_none_for_unknown_key(tmp_path):
    assert _repository(tmp_path).find_current("nope") is None


def test_save_then_find_current(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity))
    found = repository.find_current(identity.generate_key())
    assert found is not None
    assert found.execution_state is ExecutionState.SUCCESS


def test_reconstructed_artifacts_are_dehydrated(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"answer"))
    artifact = repository.find_current(identity.generate_key()).artifacts[0]
    assert artifact.content is None  # bytes live in the blob store, not the DB
    assert artifact.blob_key == "blob_" + b"answer".hex()
    assert artifact.artifact_type is ArtifactType.STDOUT
    assert artifact.size_bytes == len(b"answer")


def test_input_artifacts_round_trip_and_set_input_persisted(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    stdout = Artifact(
        artifact_type=ArtifactType.STDOUT, blob_key="blob_out", size_bytes=3, content=b"out"
    )
    prompt = Artifact(
        artifact_type=ArtifactType.INPUT_PROMPT, blob_key="blob_in", size_bytes=5, content=b"do it"
    )
    repository.save(
        MlExecution(
            call_identity=identity,
            execution_state=ExecutionState.SUCCESS,
            execution_kind=ExecutionKind.LOCAL_MANAGED,
            output_persisted=True,
            input_persisted=True,
            artifacts=[stdout, prompt],
        )
    )
    found = repository.find_current(identity.generate_key())
    # input_persisted is derived on load from the presence of INPUT_* artifacts
    assert found.input_persisted is True
    assert ArtifactType.INPUT_PROMPT in {a.artifact_type for a in found.artifacts}


def test_output_only_execution_has_input_persisted_false(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity))
    assert repository.find_current(identity.generate_key()).input_persisted is False


def test_add_input_artifacts_backfills_and_is_idempotent(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity))  # output-only entry
    key = identity.generate_key()
    assert repository.find_current(key).input_persisted is False

    prompt = Artifact(
        artifact_type=ArtifactType.INPUT_PROMPT, blob_key="blob_in", size_bytes=5, content=b"do it"
    )
    repository.add_input_artifacts(key, [prompt])
    found = repository.find_current(key)
    assert found.input_persisted is True
    assert sum(1 for a in found.artifacts if a.artifact_type is ArtifactType.INPUT_PROMPT) == 1

    # a second back-fill is a no-op -- no duplicate input rows
    repository.add_input_artifacts(key, [prompt])
    found = repository.find_current(key)
    assert sum(1 for a in found.artifacts if a.artifact_type is ArtifactType.INPUT_PROMPT) == 1


def test_add_input_artifacts_without_a_current_execution_is_a_no_op(tmp_path):
    repository = _repository(tmp_path)
    prompt = Artifact(
        artifact_type=ArtifactType.INPUT_PROMPT, blob_key="b", size_bytes=1, content=b"x"
    )
    repository.add_input_artifacts("nope", [prompt])  # must not raise


def test_failed_execution_is_not_current(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(
        _execution(
            identity,
            state=ExecutionState.FAILED,
            output_persisted=False,
            failure=ExecutionFailure(FailureReason.NONZERO_EXIT, "boom", exit_code=2),
        )
    )
    assert repository.find_current(identity.generate_key()) is None


def test_unpersisted_success_is_not_current(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, output_persisted=False))
    assert repository.find_current(identity.generate_key()) is None


# --- supersession ------------------------------------------------------------


def test_a_second_success_supersedes_the_first(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"old"))
    repository.save(_execution(identity, content=b"new"))

    current = repository.find_current(identity.generate_key())
    assert current.artifacts[0].blob_key == "blob_" + b"new".hex()

    history = repository.find_all(identity.generate_key())
    assert len(history) == 2
    assert history[0].superseded_at == _MOMENT
    assert history[1].superseded_at is None


def test_failed_refresh_does_not_supersede(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"good"))
    repository.save(_execution(identity, state=ExecutionState.FAILED, output_persisted=False))
    current = repository.find_current(identity.generate_key())
    assert current.artifacts[0].blob_key == "blob_" + b"good".hex()


# --- reconstruction ----------------------------------------------------------


def test_token_usage_round_trips(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    usage = TokenUsage(input_tokens=100, output_tokens=42, cost_usd=0.01, raw={"x": 1})
    repository.save(_execution(identity, token_usage=usage))
    restored = repository.find_current(identity.generate_key()).token_usage
    assert restored == usage


def test_add_tags_then_tags_for_returns_them_sorted(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity))
    repository.add_tags(identity.generate_key(), ["ticket", "id-scan"])
    assert repository.tags_for(identity.generate_key()) == ["id-scan", "ticket"]


def test_add_tags_is_idempotent_and_accumulates(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity))
    key = identity.generate_key()
    repository.add_tags(key, ["ticket"])
    repository.add_tags(key, ["ticket", "id-scan"])  # 'ticket' already present
    assert repository.tags_for(key) == ["id-scan", "ticket"]


def test_add_tags_is_a_no_op_without_a_current_execution(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.add_tags(identity.generate_key(), ["x"])  # nothing stored
    assert repository.tags_for(identity.generate_key()) == []


def test_failure_round_trips_in_history(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    failure = ExecutionFailure(FailureReason.NONZERO_EXIT, "client exited 2", exit_code=2)
    repository.save(
        _execution(identity, state=ExecutionState.FAILED, output_persisted=False, failure=failure)
    )
    recorded = repository.find_all(identity.generate_key())[0]
    assert recorded.failure == failure


# --- durability --------------------------------------------------------------


def test_executions_persist_across_instances(tmp_path):
    identity = _managed_identity()
    _repository(tmp_path).save(_execution(identity))
    # A fresh repository on the same file serves the stored execution.
    found = _repository(tmp_path).find_current(identity.generate_key())
    assert found is not None
    assert found.artifacts[0].blob_key == "blob_" + b"answer".hex()


# --- polymorphic identities --------------------------------------------------


def test_passthrough_identity_round_trips_through_the_store(tmp_path):
    repository = _repository(tmp_path)
    identity = PassthroughCallIdentity(client="codex", native_args_fingerprint="fp")
    repository.save(_execution(identity, kind=ExecutionKind.LOCAL_PASSTHROUGH))
    found = repository.find_current(identity.generate_key())
    assert isinstance(found.call_identity, PassthroughCallIdentity)
    assert found.call_identity.generate_key() == identity.generate_key()


def test_api_identity_round_trips_through_the_store(tmp_path):
    repository = _repository(tmp_path)
    identity = ApiCallIdentity(provider="openai", model="gpt-x", messages_fingerprint="mf")
    repository.save(_execution(identity, kind=ExecutionKind.API))
    found = repository.find_current(identity.generate_key())
    assert isinstance(found.call_identity, ApiCallIdentity)
    assert found.call_identity.provider == "openai"
    assert found.call_identity.generate_key() == identity.generate_key()


def test_different_kinds_do_not_collide_in_one_store(tmp_path):
    repository = _repository(tmp_path)
    managed = _managed_identity()
    passthrough = PassthroughCallIdentity(client="claude", native_args_fingerprint="x")
    repository.save(_execution(managed, content=b"managed"))
    repository.save(_execution(passthrough, kind=ExecutionKind.LOCAL_PASSTHROUGH, content=b"pass"))
    assert (
        repository.find_current(managed.generate_key())
        .artifacts[0]
        .blob_key.endswith(b"managed".hex())
    )
    assert (
        repository.find_current(passthrough.generate_key())
        .artifacts[0]
        .blob_key.endswith(b"pass".hex())
    )
