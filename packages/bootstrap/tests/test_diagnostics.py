# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The driver-facing diagnostics factory (W28).

Drivers resolve their own logging policy (level + file) and hand it here; the
composition root builds the concrete port so the driver imports no
``adapters.…diagnostics`` class.
"""

from pathlib import Path

import pytest
from generic_ml_cache_adapters.adapter.outbound.diagnostics.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_adapters.adapter.outbound.diagnostics.structlog_diagnostics_adapter import (
    StructlogDiagnosticsAdapter,
)

from generic_ml_cache_bootstrap.diagnostics import build_diagnostics


def test_absent_level_yields_the_quiet_null_adapter():
    assert isinstance(build_diagnostics(None), NullDiagnosticsAdapter)
    assert isinstance(build_diagnostics(""), NullDiagnosticsAdapter)


def test_level_with_file_yields_structlog_and_creates_the_parent_dir(tmp_path: Path):
    log_file = tmp_path / "nested" / "gmlcache.log"
    diag = build_diagnostics("INFO", log_file)
    assert isinstance(diag, StructlogDiagnosticsAdapter)
    assert log_file.parent.is_dir()


def test_level_without_file_is_a_contract_error():
    with pytest.raises(ValueError, match="log file is required"):
        build_diagnostics("INFO", None)
