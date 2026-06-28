# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from unittest.mock import create_autospec, MagicMock

from generic_ml_cache_core.application.domain.model.execution.artifact import ArtifactType
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.identity.api_call_identity import (
    ApiCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.domain.model.identity.passthrough_call_identity import (
    PassthroughCallIdentity,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (
    RunMlExecutionCommand,
)
from generic_ml_cache_core.application.port.out.blob_store_port import BlobStorePort
from generic_ml_cache_core.application.port.out.execution_repository_port import (
    ExecutionRepositoryPort,
)
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.application.port.out.metrics_port import MetricsPort
from generic_ml_cache_core.application.usecase.purge_service import PurgeService
from generic_ml_cache_core.application.usecase.run_ml_execution_service import RunMlExecutionService


def _make_svc(file_fingerprint=None, runners=None, purge_service=None, max_size=None):
    return RunMlExecutionService(
        file_fingerprint=file_fingerprint or create_autospec(FileFingerprintPort),
        runners=runners or {},
        blob_store=create_autospec(BlobStorePort),
        repository=create_autospec(ExecutionRepositoryPort),
        metrics=create_autospec(MetricsPort),
        purge_service=purge_service,
        max_size=max_size,
    )


def _cmd(
    kind=ExecutionKind.LOCAL_MANAGED, client="claude", model="sonnet", effort="high", **kwargs
):
    return RunMlExecutionCommand(
        execution_kind=kind, client=client, model=model, effort=effort, **kwargs
    )


class TestBuildIdentity:
    def test_local_managed_returns_managed_call_identity(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED)
        identity = svc._build_identity(cmd)
        assert isinstance(identity, ManagedCallIdentity)

    def test_local_managed_uses_file_fingerprint(self):
        fp = create_autospec(FileFingerprintPort)
        fp.fingerprint.return_value = "fp_abc"
        svc = _make_svc(file_fingerprint=fp)
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED, input_file_paths=["/a/file.txt"])
        svc._build_identity(cmd)
        fp.fingerprint.assert_called_once_with("/a/file.txt")

    def test_local_passthrough_returns_passthrough_call_identity(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_PASSTHROUGH)
        identity = svc._build_identity(cmd)
        assert isinstance(identity, PassthroughCallIdentity)

    def test_local_passthrough_client_field_matches_command(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_PASSTHROUGH, client="pass-claude")
        identity = svc._build_identity(cmd)
        assert identity.client == "pass-claude"

    def test_api_returns_api_call_identity(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.API)
        identity = svc._build_identity(cmd)
        assert isinstance(identity, ApiCallIdentity)

    def test_api_provider_and_model_fields(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.API, client="anthropic", model="claude-3-7")
        identity = svc._build_identity(cmd)
        assert identity.provider == "anthropic"
        assert identity.model == "claude-3-7"


class TestRunClient:
    def test_runner_exists_calls_runner_run(self):
        runner = MagicMock()
        svc = _make_svc(runners={ExecutionKind.LOCAL_MANAGED: runner})
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED, prompt="hello")
        svc._run_client(cmd)
        runner.run.assert_called_once()

    def test_runner_exists_returns_runner_result(self):
        expected = MagicMock()
        runner = MagicMock()
        runner.run.return_value = expected
        svc = _make_svc(runners={ExecutionKind.API: runner})
        cmd = _cmd(kind=ExecutionKind.API, prompt="q")
        result = svc._run_client(cmd)
        assert result is expected

    def test_no_runner_raises_runtime_error(self):
        svc = _make_svc(runners={})
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED)
        with pytest.raises(RuntimeError):
            svc._run_client(cmd)


class TestAfterRecord:
    def test_purge_service_none_does_not_evict(self):
        svc = _make_svc(purge_service=None, max_size=1000)
        svc._after_record("key")

    def test_max_size_none_does_not_evict(self):
        purge_mock = create_autospec(PurgeService)
        svc = _make_svc(purge_service=purge_mock, max_size=None)
        svc._after_record("key")
        purge_mock.evict_to_quota.assert_not_called()

    def test_both_set_calls_evict_to_quota(self):
        purge_mock = create_autospec(PurgeService)
        svc = _make_svc(purge_service=purge_mock, max_size=5000)
        svc._after_record("key")
        purge_mock.evict_to_quota.assert_called_once_with(5000)


class TestJournalFields:
    def test_local_passthrough_returns_client_empty_empty(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_PASSTHROUGH, client="pass-claude", model="", effort="")
        result = svc._journal_fields(cmd)
        assert result == ("pass-claude", "", "")

    def test_local_managed_returns_client_model_effort(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED, client="claude", model="opus", effort="max")
        result = svc._journal_fields(cmd)
        assert result == ("claude", "opus", "max")

    def test_api_returns_client_model_effort(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.API, client="anthropic", model="claude-3-7", effort="")
        result = svc._journal_fields(cmd)
        assert result == ("anthropic", "claude-3-7", "")


class TestExecutionKind:
    def test_delegates_to_command_execution_kind(self):
        svc = _make_svc()
        for kind in ExecutionKind:
            cmd = _cmd(kind=kind)
            assert svc._execution_kind(cmd) is kind


class TestIsUncacheable:
    def test_cacheable_managed_command_returns_false(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED, allow_paths=[], scan_trust=False)
        assert svc._is_uncacheable(cmd) is False

    def test_uncacheable_managed_command_with_allow_paths_returns_true(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED, allow_paths=["/some/dir"], scan_trust=False)
        assert svc._is_uncacheable(cmd) is True

    def test_scan_trust_overrides_allow_paths(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED, allow_paths=["/some/dir"], scan_trust=True)
        assert svc._is_uncacheable(cmd) is False

    def test_api_is_always_cacheable(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.API)
        assert svc._is_uncacheable(cmd) is False

    def test_passthrough_is_always_cacheable(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_PASSTHROUGH)
        assert svc._is_uncacheable(cmd) is False


class TestExecutionTags:
    def test_strips_and_sorts_tags(self):
        svc = _make_svc()
        cmd = _cmd(tags=["  Tag1  ", "tag2"])
        result = svc._execution_tags(cmd)
        assert result == ["Tag1", "tag2"]

    def test_empty_tags_returns_empty_list(self):
        svc = _make_svc()
        cmd = _cmd(tags=[])
        assert svc._execution_tags(cmd) == []

    def test_deduplicates_tags(self):
        svc = _make_svc()
        cmd = _cmd(tags=["foo", "foo", "bar"])
        result = svc._execution_tags(cmd)
        assert result == ["bar", "foo"]

    def test_drops_blank_tags(self):
        svc = _make_svc()
        cmd = _cmd(tags=["  ", "", "valid"])
        result = svc._execution_tags(cmd)
        assert result == ["valid"]


class TestInputParts:
    def test_local_passthrough_returns_input_args_tuple(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_PASSTHROUGH, native_args=["--foo", "bar"])
        parts = svc._input_parts(cmd)
        assert len(parts) == 1
        assert parts[0][0] is ArtifactType.INPUT_ARGS
        assert parts[0][1] is None
        assert parts[0][2] == b'["--foo", "bar"]'

    def test_local_managed_with_context_prompt_system_returns_three_parts(self):
        svc = _make_svc()
        cmd = _cmd(
            kind=ExecutionKind.LOCAL_MANAGED,
            context="ctx",
            prompt="pmt",
            user_system_prompt="sys",
        )
        parts = svc._input_parts(cmd)
        types = [p[0] for p in parts]
        assert types == [
            ArtifactType.INPUT_CONTEXT,
            ArtifactType.INPUT_PROMPT,
            ArtifactType.INPUT_SYSTEM,
        ]

    def test_local_managed_with_only_prompt_returns_one_part(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.LOCAL_MANAGED, context="", prompt="only prompt")
        parts = svc._input_parts(cmd)
        assert len(parts) == 1
        assert parts[0][0] is ArtifactType.INPUT_PROMPT
        assert parts[0][2] == b"only prompt"

    def test_api_with_prompt_returns_input_prompt_part(self):
        svc = _make_svc()
        cmd = _cmd(kind=ExecutionKind.API, context="", prompt="api question")
        parts = svc._input_parts(cmd)
        assert len(parts) == 1
        assert parts[0][0] is ArtifactType.INPUT_PROMPT
        assert parts[0][2] == b"api question"
