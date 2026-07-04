# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for SqliteExecutionRepository."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

import pytest
from generic_ml_cache_core.application.domain.model.execution.artifact import (
    Artifact,
    ArtifactStatus,
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
    ExecutionFailure,
    FailureReason,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.execution.execution_state import ExecutionState
from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution
from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)
from generic_ml_cache_core.application.domain.model.usage.token_usage import TokenUsage
from generic_ml_cache_core.application.port.outbound.clock_port import ClockPort
from generic_ml_cache_core.application.port.outbound.ml_run_ports import (
    AnnotateMlRunPort,
    InspectMlRunsPort,
    PurgeMlRunsPort,
    ReadMlRunPort,
    SaveMlRunPort,
)

from generic_ml_cache_adapters.adapter.outbound.persistence.sqlite.execution_repository import (
    SqliteExecutionRepository,
)
from generic_ml_cache_adapters.db import DbCursor
from generic_ml_cache_adapters.migration_runner import run_migrations

_MOMENT = datetime(2026, 6, 21, 9, 30, tzinfo=timezone.utc)


class FixedClock(ClockPort):
    def now(self) -> datetime:
        return _MOMENT


class _NullCursor:
    lastrowid: int | None = 0
    rowcount: int = 0

    def fetchone(self) -> Any:
        return None

    def fetchall(self) -> list[Any]:
        return []


class _RecordingConnection:
    """A DbConnection spy that records the transaction calls it receives, so a
    test can assert the write helper commits on success / rolls back on error."""

    def __init__(self, *, fail_on_execute: bool = False) -> None:
        self.calls: list[str] = []
        self._fail_on_execute = fail_on_execute

    def execute(self, sql: str, parameters: Any = ()) -> DbCursor:
        self.calls.append("execute")
        if self._fail_on_execute:
            raise sqlite3.OperationalError("simulated write failure")
        return _NullCursor()

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def close(self) -> None:
        self.calls.append("close")


def test_write_commits_then_closes_on_success(tmp_path):
    connection = _RecordingConnection()
    repository = SqliteExecutionRepository(lambda: connection, clock=FixedClock())
    repository.mark_artifacts_stored("some-key", "some-blob")
    assert connection.calls == ["execute", "commit", "close"]


def test_write_rolls_back_then_closes_on_error(tmp_path):
    connection = _RecordingConnection(fail_on_execute=True)
    repository = SqliteExecutionRepository(lambda: connection, clock=FixedClock())
    with pytest.raises(sqlite3.OperationalError):
        repository.mark_artifacts_stored("some-key", "some-blob")
    # Rollback is explicit — never a silent reliance on close-time auto-rollback —
    # and commit is never reached on the error path.
    assert connection.calls == ["execute", "rollback", "close"]


def _make_factory(db_path):
    def _connect():
        return sqlite3.connect(str(db_path))

    return _connect


def _repository(tmp_path) -> SqliteExecutionRepository:
    factory = _make_factory(tmp_path / "executions.sqlite3")
    run_migrations(factory)
    return SqliteExecutionRepository(factory, clock=FixedClock())


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


def test_implements_ml_run_ports(tmp_path):
    repository = _repository(tmp_path)
    assert isinstance(repository, SaveMlRunPort)
    assert isinstance(repository, ReadMlRunPort)
    assert isinstance(repository, AnnotateMlRunPort)
    assert isinstance(repository, InspectMlRunsPort)
    assert isinstance(repository, PurgeMlRunsPort)


def test_find_current_is_none_for_unknown_key(tmp_path):
    assert _repository(tmp_path).find_current("nope") is None


def test_execution_id_round_trips_through_save_and_reload(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    execution = _execution(identity)
    repository.save(execution)
    reloaded = repository.find_all(identity.generate_key())
    assert len(reloaded) == 1
    assert reloaded[0].execution_id == execution.execution_id


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
    identity = ApiCallIdentity(
        provider="openai", model="gpt-x", context_fingerprint="cf", prompt_fingerprint="pf"
    )
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


# --- blob_keys_for_execution -------------------------------------------------


def test_blob_keys_for_execution_returns_all_blob_keys(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"answer"))
    keys = repository.blob_keys_for_execution(identity.generate_key())
    assert keys == ["blob_" + b"answer".hex()]


def test_blob_keys_for_execution_unknown_key_returns_empty(tmp_path):
    assert _repository(tmp_path).blob_keys_for_execution("nope") == []


def test_blob_keys_for_execution_includes_superseded_executions(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"old"))
    repository.save(_execution(identity, content=b"new"))
    keys = set(repository.blob_keys_for_execution(identity.generate_key()))
    assert "blob_" + b"old".hex() in keys
    assert "blob_" + b"new".hex() in keys


# --- blob_reference_count ----------------------------------------------------


def test_blob_reference_count_is_one_for_a_single_execution(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"answer"))
    blob_key = "blob_" + b"answer".hex()
    assert repository.blob_reference_count(blob_key) == 1


def test_blob_reference_count_is_zero_for_unknown_blob(tmp_path):
    assert _repository(tmp_path).blob_reference_count("nope") == 0


def test_blob_reference_count_counts_all_referencing_rows(tmp_path):
    repository = _repository(tmp_path)
    id_a = _managed_identity(prompt_fingerprint="a")
    id_b = _managed_identity(prompt_fingerprint="b")
    shared_blob = "blob_shared"

    # Two executions with identical content (same blob_key — content-addressed)
    def _shared_execution(identity):
        artifact = Artifact(
            artifact_type=ArtifactType.STDOUT,
            blob_key=shared_blob,
            size_bytes=6,
            content=b"shared",
        )
        return MlExecution(
            call_identity=identity,
            execution_state=ExecutionState.SUCCESS,
            execution_kind=ExecutionKind.LOCAL_MANAGED,
            output_persisted=True,
            artifacts=[artifact],
        )

    repository.save(_shared_execution(id_a))
    repository.save(_shared_execution(id_b))
    assert repository.blob_reference_count(shared_blob) == 2


# --- soft_purge_execution ----------------------------------------------------


def test_soft_purge_removes_artifacts(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"answer"))
    key = identity.generate_key()
    repository.soft_purge_execution(key)
    history = repository.find_all(key)
    assert len(history) == 1
    assert history[0].artifacts == []


def test_soft_purge_makes_execution_not_current(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity))
    key = identity.generate_key()
    repository.soft_purge_execution(key)
    assert repository.find_current(key) is None


def test_soft_purge_preserves_token_usage(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    usage = TokenUsage(input_tokens=10, output_tokens=5, raw={"x": 1})
    repository.save(_execution(identity, token_usage=usage))
    key = identity.generate_key()
    repository.soft_purge_execution(key)
    history = repository.find_all(key)
    assert len(history) == 1
    assert history[0].token_usage == usage


def test_soft_purge_reduces_blob_reference_count_to_zero(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"answer"))
    blob_key = "blob_" + b"answer".hex()
    assert repository.blob_reference_count(blob_key) == 1
    repository.soft_purge_execution(identity.generate_key())
    assert repository.blob_reference_count(blob_key) == 0


def test_soft_purge_does_not_drop_shared_blob_reference(tmp_path):
    repository = _repository(tmp_path)
    id_a = _managed_identity(prompt_fingerprint="a")
    id_b = _managed_identity(prompt_fingerprint="b")
    shared_blob = "blob_shared"

    def _shared(identity):
        artifact = Artifact(
            artifact_type=ArtifactType.STDOUT,
            blob_key=shared_blob,
            size_bytes=6,
            content=b"shared",
        )
        return MlExecution(
            call_identity=identity,
            execution_state=ExecutionState.SUCCESS,
            execution_kind=ExecutionKind.LOCAL_MANAGED,
            output_persisted=True,
            artifacts=[artifact],
        )

    repository.save(_shared(id_a))
    repository.save(_shared(id_b))
    repository.soft_purge_execution(id_a.generate_key())
    # id_b still holds a reference — blob should not be deleted yet
    assert repository.blob_reference_count(shared_blob) == 1


def test_soft_purge_unknown_key_is_a_no_op(tmp_path):
    _repository(tmp_path).soft_purge_execution("nope")  # must not raise


# --- hard_delete_execution ---------------------------------------------------


def test_hard_delete_execution_removes_all_history(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"v1"))
    repository.save(_execution(identity, content=b"v2"))
    key = identity.generate_key()
    repository.hard_delete_execution(key)
    assert repository.find_current(key) is None
    assert repository.find_all(key) == []


def test_hard_delete_execution_removes_blob_references(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"answer"))
    blob_key = "blob_" + b"answer".hex()
    repository.hard_delete_execution(identity.generate_key())
    assert repository.blob_reference_count(blob_key) == 0


def test_hard_delete_execution_allows_re_save_of_same_key(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"first"))
    repository.hard_delete_execution(identity.generate_key())
    repository.save(_execution(identity, content=b"second"))
    found = repository.find_current(identity.generate_key())
    assert found is not None
    assert found.artifacts[0].blob_key == "blob_" + b"second".hex()


def test_hard_delete_unknown_key_is_a_no_op(tmp_path):
    _repository(tmp_path).hard_delete_execution("nope")  # must not raise


# --- total_stored_bytes ------------------------------------------------------


def test_total_stored_bytes_is_zero_for_empty_store(tmp_path):
    assert _repository(tmp_path).total_stored_bytes() == 0


def test_total_stored_bytes_sums_current_executions(tmp_path):
    repository = _repository(tmp_path)
    id_a = _managed_identity(prompt_fingerprint="a")
    id_b = _managed_identity(prompt_fingerprint="b")
    repository.save(_execution(id_a, content=b"abc"))  # 3 bytes
    repository.save(_execution(id_b, content=b"de"))  # 2 bytes
    assert repository.total_stored_bytes() == 5


def test_total_stored_bytes_excludes_superseded_executions(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"old123"))  # superseded
    repository.save(_execution(identity, content=b"new"))  # current: 3 bytes
    assert repository.total_stored_bytes() == 3


def test_total_stored_bytes_drops_to_zero_after_soft_purge(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"answer"))
    repository.soft_purge_execution(identity.generate_key())
    assert repository.total_stored_bytes() == 0


# --- current_executions_with_sizes -------------------------------------------


def test_current_executions_with_sizes_empty_store(tmp_path):
    assert _repository(tmp_path).current_executions_with_sizes() == []


def test_current_executions_with_sizes_returns_correct_totals(tmp_path):
    repository = _repository(tmp_path)
    id_a = _managed_identity(prompt_fingerprint="a")
    id_b = _managed_identity(prompt_fingerprint="b")
    repository.save(_execution(id_a, content=b"abc"))  # 3 bytes
    repository.save(_execution(id_b, content=b"de"))  # 2 bytes
    entries = {
        e.execution_key: e.total_size_bytes for e in repository.current_executions_with_sizes()
    }
    assert entries[id_a.generate_key()] == 3
    assert entries[id_b.generate_key()] == 2


def test_current_executions_with_sizes_excludes_superseded(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity, content=b"old123"))  # superseded
    repository.save(_execution(identity, content=b"new"))  # current: 3 bytes
    entries = repository.current_executions_with_sizes()
    assert len(entries) == 1
    assert entries[0].total_size_bytes == 3


# --- executions_by_tag -------------------------------------------------------


def test_executions_by_tag_returns_matching_keys(tmp_path):
    repository = _repository(tmp_path)
    id_a = _managed_identity(prompt_fingerprint="a")
    id_b = _managed_identity(prompt_fingerprint="b")
    repository.save(_execution(id_a))
    repository.save(_execution(id_b))
    repository.add_tags(id_a.generate_key(), ["important"])
    repository.add_tags(id_b.generate_key(), ["other"])
    keys = repository.executions_by_tag("important")
    assert keys == [id_a.generate_key()]


def test_executions_by_tag_no_match_returns_empty(tmp_path):
    assert _repository(tmp_path).executions_by_tag("nope") == []


def test_executions_by_tag_excludes_purged_executions(tmp_path):
    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(_execution(identity))
    key = identity.generate_key()
    repository.add_tags(key, ["work"])
    repository.soft_purge_execution(key)
    assert repository.executions_by_tag("work") == []


# --- all_execution_keys ------------------------------------------------------


def test_all_execution_keys_empty_store(tmp_path):
    assert _repository(tmp_path).all_execution_keys() == []


def test_all_execution_keys_returns_all_keys(tmp_path):
    repository = _repository(tmp_path)
    id_a = _managed_identity(prompt_fingerprint="a")
    id_b = _managed_identity(prompt_fingerprint="b")
    repository.save(_execution(id_a))
    repository.save(_execution(id_b))
    keys = set(repository.all_execution_keys())
    assert id_a.generate_key() in keys
    assert id_b.generate_key() in keys


def test_all_execution_keys_includes_failed_only_keys(tmp_path):
    from generic_ml_cache_core.application.domain.model.execution.execution_failure import (
        ExecutionFailure,
        FailureReason,
    )

    repository = _repository(tmp_path)
    identity = _managed_identity()
    repository.save(
        _execution(
            identity,
            state=ExecutionState.FAILED,
            output_persisted=False,
            failure=ExecutionFailure(FailureReason.NONZERO_EXIT, "boom", exit_code=1),
        )
    )
    assert identity.generate_key() in repository.all_execution_keys()


def test_all_execution_keys_empty_after_hard_delete_all(tmp_path):
    repository = _repository(tmp_path)
    id_a = _managed_identity(prompt_fingerprint="a")
    id_b = _managed_identity(prompt_fingerprint="b")
    repository.save(_execution(id_a))
    repository.save(_execution(id_b))
    for key in list(repository.all_execution_keys()):
        repository.hard_delete_execution(key)
    assert repository.all_execution_keys() == []


# --- C-4 DB-first artifact lifecycle -----------------------------------------


def _pending_execution(identity, *, state=ExecutionState.SUCCESS, content=b"answer"):
    """An execution as the DB-first write path saves it: not-yet-persisted, with a
    PENDING artifact whose blob has not been stored."""
    artifact = Artifact(
        artifact_type=ArtifactType.STDOUT,
        blob_key="blob_" + content.hex(),
        size_bytes=len(content),
        content=content,
        status=ArtifactStatus.PENDING,
    )
    return MlExecution(
        call_identity=identity,
        execution_state=state,
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        output_persisted=False,
        artifacts=[artifact],
    )


def test_db_first_pending_run_is_not_servable_until_finalized(tmp_path):
    repo = _repository(tmp_path)
    identity = _managed_identity()
    key = identity.generate_key()
    execution = _pending_execution(identity)
    blob_key = execution.artifacts[0].blob_key

    repo.save(execution)  # PENDING, output_persisted=0 -> not servable, no supersede
    assert repo.find_current(key) is None
    assert repo.find_all(key)[0].artifacts[0].status is ArtifactStatus.PENDING

    repo.mark_artifacts_stored(key, blob_key)
    stored = repo.find_all(key)[0].artifacts[0]
    assert stored.status is ArtifactStatus.STORED
    assert stored.persisted_at is not None
    assert repo.find_current(key) is None  # still not finalized

    repo.finalize_output_persisted(key)
    current = repo.find_current(key)
    assert current is not None
    assert current.output_persisted is True


def test_db_first_failed_blob_marks_artifact_failed(tmp_path):
    repo = _repository(tmp_path)
    identity = _managed_identity()
    key = identity.generate_key()
    execution = _pending_execution(identity)
    blob_key = execution.artifacts[0].blob_key

    repo.save(execution)
    repo.mark_artifacts_failed(key, blob_key, "disk full")
    failed = repo.find_all(key)[0].artifacts[0]
    assert failed.status is ArtifactStatus.FAILED
    assert failed.status_detail == "disk full"
    # A FAILED artifact does not keep the blob alive for GC.
    assert repo.blob_reference_count(blob_key) == 0
    # Never finalized -> not servable.
    assert repo.find_current(key) is None


def test_finalizing_a_recorded_failure_does_not_supersede_the_good_answer(tmp_path):
    # record_on_error stores a FAILED run; finalizing it must persist the record
    # WITHOUT displacing the current SUCCESS (find_current filters SUCCESS anyway).
    repo = _repository(tmp_path)
    identity = _managed_identity()
    key = identity.generate_key()

    good = _pending_execution(identity, content=b"good")
    repo.save(good)
    repo.mark_artifacts_stored(key, good.artifacts[0].blob_key)
    repo.finalize_output_persisted(key)
    assert repo.find_current(key) is not None

    failed = _pending_execution(identity, state=ExecutionState.FAILED, content=b"boom")
    repo.save(failed)
    repo.mark_artifacts_stored(key, failed.artifacts[0].blob_key)
    repo.finalize_output_persisted(key)

    current = repo.find_current(key)
    assert current is not None
    assert current.execution_state is ExecutionState.SUCCESS
    assert current.artifacts[0].blob_key == "blob_" + b"good".hex()


def test_corrupt_blob_key_in_db_is_rejected_on_load(tmp_path):
    # C-5 parse-at-edge: a traversal-unsafe key that somehow reached the DB (row
    # corruption/tampering) is rejected when the repository reconstructs the
    # Artifact — it never reaches the blob store.
    repo = _repository(tmp_path)
    identity = _managed_identity()
    key = identity.generate_key()
    repo.save(_execution(identity))

    factory = _make_factory(tmp_path / "executions.sqlite3")
    conn = factory()
    try:
        conn.execute("UPDATE artifacts SET blob_key = ?", ("../etc/passwd",))
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(ValueError, match="invalid blob key"):
        repo.find_current(key)
