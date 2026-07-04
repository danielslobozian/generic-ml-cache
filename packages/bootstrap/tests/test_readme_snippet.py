# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Regression guard for the root README's "Five packages" embed snippet (V1).

The flagship "how to embed the engine" example must always import and wire, so a
rename like WiredUseCases -> ApplicationApi can never leave a broken snippet.
"""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.port.inbound.run_ml_execution.run_ml_execution_command import (
    RunMlExecutionCommand,
)

from generic_ml_cache_bootstrap.application import build_application_api


def test_readme_embed_snippet_imports_and_wires(tmp_path) -> None:
    wired = build_application_api(tmp_path, lambda _catalog, _resolver: {})
    assert wired.run_ml is not None
    command = RunMlExecutionCommand(
        execution_kind=ExecutionKind.LOCAL_MANAGED, client="claude", model="m"
    )
    assert wired.run_ml.execute is not None and command is not None
