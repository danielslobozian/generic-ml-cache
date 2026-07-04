# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the core adapter-catalog services.

These run against a pure in-test catalog — no installed adapters, no entry-point
scanning — which is exactly the point: core's availability/selection/validation
logic is testable as a pure library.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from generic_ml_cache_core.application.domain.model.catalog.adapter_boundary import AdapterBoundary
from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.usecase.check_client_availability_service import (
    CheckClientAvailabilityService,
)
from generic_ml_cache_core.application.usecase.select_adapter_for_execution_service import (
    SelectAdapterForExecutionService,
)
from generic_ml_cache_core.application.usecase.validate_execution_mode_service import (
    ValidateExecutionModeService,
)
from generic_ml_cache_core.common.errors import (
    CapabilityUnavailable,
    UnknownClient,
    UnsupportedExecutionMode,
)


class FakeCatalog:
    """A static in-memory AdapterCatalogPort for pure-core tests."""

    def __init__(self, *descriptors: AdapterDescriptor) -> None:
        self._descriptors = list(descriptors)

    def list_adapters(self) -> Sequence[AdapterDescriptor]:
        return list(self._descriptors)

    def find_by_client_name(self, client_name: str) -> Sequence[AdapterDescriptor]:
        return [d for d in self._descriptors if d.client_name == client_name]

    def supports(self, client_name: str, mode: ExecutionKind) -> bool:
        return any(
            d.client_name == client_name and d.supports_mode(mode) for d in self._descriptors
        )


def _claude() -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id="claude.cli",
        client_name="claude",
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=frozenset({ExecutionKind.LOCAL_MANAGED, ExecutionKind.LOCAL_PASSTHROUGH}),
        capabilities=frozenset({ClientCapability.RUN}),
    )


def _cursor() -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id="cursor.cli",
        client_name="cursor",
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=frozenset({ExecutionKind.LOCAL_MANAGED, ExecutionKind.LOCAL_PASSTHROUGH}),
        capabilities=frozenset({ClientCapability.RUN, ClientCapability.LIST_MODELS}),
    )


def _anthropic() -> AdapterDescriptor:
    return AdapterDescriptor(
        adapter_id="anthropic.api",
        client_name="anthropic",
        boundary=AdapterBoundary.API,
        supported_modes=frozenset({ExecutionKind.API}),
        capabilities=frozenset({ClientCapability.RUN, ClientCapability.LIST_MODELS}),
    )


# --- CheckClientAvailabilityService ------------------------------------------


def test_available_client_reports_available_with_candidates():
    svc = CheckClientAvailabilityService(FakeCatalog(_claude()))
    result = svc.check("claude")
    assert result.available is True
    assert [d.adapter_id for d in result.candidates] == ["claude.cli"]


def test_absent_client_reports_unavailable():
    svc = CheckClientAvailabilityService(FakeCatalog(_claude()))
    result = svc.check("cursor")
    assert result.available is False
    assert result.candidates == ()


# --- SelectAdapterForExecutionService ----------------------------------------


def test_select_by_client_and_mode():
    svc = SelectAdapterForExecutionService(FakeCatalog(_claude(), _anthropic()))
    chosen = svc.select("claude", ExecutionKind.LOCAL_MANAGED)
    assert chosen.adapter_id == "claude.cli"


def test_select_unknown_client_raises():
    svc = SelectAdapterForExecutionService(FakeCatalog(_claude()))
    with pytest.raises(UnknownClient):
        svc.select("nope", ExecutionKind.LOCAL_MANAGED)


def test_select_unsupported_mode_raises():
    svc = SelectAdapterForExecutionService(FakeCatalog(_claude()))
    with pytest.raises(UnsupportedExecutionMode):
        svc.select("claude", ExecutionKind.API)


def test_select_missing_capability_raises():
    svc = SelectAdapterForExecutionService(FakeCatalog(_claude()))  # claude: RUN only
    with pytest.raises(CapabilityUnavailable):
        svc.select(
            "claude",
            ExecutionKind.LOCAL_MANAGED,
            required_capabilities=[ClientCapability.LIST_MODELS],
        )


def test_select_with_satisfied_capability():
    svc = SelectAdapterForExecutionService(FakeCatalog(_cursor()))
    chosen = svc.select(
        "cursor",
        ExecutionKind.LOCAL_MANAGED,
        required_capabilities=[ClientCapability.LIST_MODELS],
    )
    assert chosen.adapter_id == "cursor.cli"


def test_select_highest_priority_wins():
    low = AdapterDescriptor(
        adapter_id="claude.alt",
        client_name="claude",
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=frozenset({ExecutionKind.LOCAL_MANAGED}),
        priority=1,
    )
    high = AdapterDescriptor(
        adapter_id="claude.cli",
        client_name="claude",
        boundary=AdapterBoundary.LOCAL_CLI,
        supported_modes=frozenset({ExecutionKind.LOCAL_MANAGED}),
        priority=9,
    )
    svc = SelectAdapterForExecutionService(FakeCatalog(low, high))
    assert svc.select("claude", ExecutionKind.LOCAL_MANAGED).adapter_id == "claude.cli"


# --- ValidateExecutionModeService --------------------------------------------


def test_validate_supported_mode_passes():
    svc = ValidateExecutionModeService(FakeCatalog(_claude()))
    svc.validate("claude", ExecutionKind.LOCAL_PASSTHROUGH)  # no raise


def test_validate_unknown_client_raises_unknown():
    svc = ValidateExecutionModeService(FakeCatalog(_claude()))
    with pytest.raises(UnknownClient):
        svc.validate("nope", ExecutionKind.LOCAL_MANAGED)


def test_validate_present_client_wrong_mode_raises_unsupported():
    svc = ValidateExecutionModeService(FakeCatalog(_claude()))
    with pytest.raises(UnsupportedExecutionMode):
        svc.validate("claude", ExecutionKind.API)
