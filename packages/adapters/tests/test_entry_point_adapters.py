# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the entry-point adapter discovery mechanism (0.21.0).

Each test resets the module-level entry-point state via the ``_reset_ep_state``
fixture so tests are independent of load order and of each other.
"""

from __future__ import annotations

import warnings
from unittest.mock import MagicMock

import pytest

import generic_ml_cache_core.adapter.registry as reg
from generic_ml_cache_core.adapter.registry import (
    ADAPTER_CONTRACT_VERSION,
    adapter_sources,
    load_adapters,
)
from generic_ml_cache_adapters.adapter.out.api.stub_api_client_adapter import StubApiClientAdapter


def _make_ep(
    adapter_cls: type,
    ep_key: str | None = None,
    dist_name: str = "test-pkg",
    dist_version: str = "1.0.0",
) -> MagicMock:
    """Build a minimal mock entry-point that loads ``adapter_cls``."""
    dist = MagicMock()
    dist.metadata.get.side_effect = lambda key, default="": {
        "Name": dist_name,
        "Version": dist_version,
    }.get(key, default)

    ep = MagicMock()
    ep.name = ep_key or getattr(adapter_cls, "name", "unknown-ep")
    ep.value = f"test_module:{adapter_cls.__name__}"
    ep.load.return_value = adapter_cls
    ep.dist = dist
    return ep


@pytest.fixture(autouse=True)
def _reset_ep_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate entry-point global state for each test."""
    monkeypatch.setattr(reg, "_ENTRYPOINTS_LOADED", False)
    monkeypatch.setattr(reg, "_ENTRYPOINT_INSTANCES", {})
    monkeypatch.setattr(reg, "_ENTRYPOINT_SOURCES", {})


# ---------------------------------------------------------------------------
# Contract version constant
# ---------------------------------------------------------------------------


def test_adapter_contract_version_is_defined_and_stable() -> None:
    assert ADAPTER_CONTRACT_VERSION == "1"


# ---------------------------------------------------------------------------
# No entry points installed
# ---------------------------------------------------------------------------


def test_empty_entry_point_group_adds_no_adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [])
    result = load_adapters()
    assert "ep-absent" not in result


# ---------------------------------------------------------------------------
# Successful entry-point loading
# ---------------------------------------------------------------------------


def test_entry_point_adapter_is_included_in_load_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EpAdapter(StubApiClientAdapter):
        name = "ep-present"

    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [_make_ep(_EpAdapter)])
    result = load_adapters()
    assert "ep-present" in result


def test_entry_point_adapter_with_correct_contract_version_is_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EpAdapter(StubApiClientAdapter):
        name = "ep-compat"
        adapter_contract_version = ADAPTER_CONTRACT_VERSION

    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [_make_ep(_EpAdapter)])
    result = load_adapters()
    assert "ep-compat" in result


def test_entry_point_adapter_without_contract_version_is_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EpAdapter(StubApiClientAdapter):
        name = "ep-no-version"

    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [_make_ep(_EpAdapter)])
    result = load_adapters()
    assert "ep-no-version" in result


# ---------------------------------------------------------------------------
# Source reporting
# ---------------------------------------------------------------------------


def test_adapter_sources_returns_source_for_loaded_ep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EpAdapter(StubApiClientAdapter):
        name = "ep-sourced"

    monkeypatch.setattr(
        reg,
        "_entry_points_for_group",
        lambda: [_make_ep(_EpAdapter, dist_name="my-adapter-pkg", dist_version="2.3.0")],
    )
    sources = adapter_sources()
    assert sources.get("ep-sourced") == "my-adapter-pkg 2.3.0"


def test_adapter_sources_excludes_builtin_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [])
    sources = adapter_sources()
    assert "claude" not in sources
    assert "anthropic" not in sources


def test_adapter_sources_respects_whitelist(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EpA(StubApiClientAdapter):
        name = "ep-a"

    class _EpB(StubApiClientAdapter):
        name = "ep-b"

    monkeypatch.setattr(
        reg,
        "_entry_points_for_group",
        lambda: [_make_ep(_EpA), _make_ep(_EpB)],
    )
    sources = adapter_sources(whitelist=frozenset({"ep-a"}))
    assert "ep-a" in sources
    assert "ep-b" not in sources


# ---------------------------------------------------------------------------
# Contract version incompatibility
# ---------------------------------------------------------------------------


def test_incompatible_contract_version_is_skipped_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _OldAdapter(StubApiClientAdapter):
        name = "ep-old"
        adapter_contract_version = "0"

    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [_make_ep(_OldAdapter)])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = load_adapters()

    assert "ep-old" not in result
    assert any("contract version" in str(warning.message) for warning in caught)


# ---------------------------------------------------------------------------
# Missing or empty name
# ---------------------------------------------------------------------------


def test_adapter_with_no_name_attribute_is_skipped_with_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoNameAdapter(StubApiClientAdapter):
        name = ""

    ep = _make_ep(_NoNameAdapter, ep_key="ep-nameless")
    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [ep])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = load_adapters()

    assert "ep-nameless" not in result
    assert "" not in result
    assert any("no 'name'" in str(warning.message) for warning in caught)


# ---------------------------------------------------------------------------
# Load failures
# ---------------------------------------------------------------------------


def test_load_failure_is_warned_and_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    ep = MagicMock()
    ep.name = "ep-broken"
    ep.load.side_effect = ImportError("missing dependency")
    ep.dist = None

    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [ep])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = load_adapters()

    assert "ep-broken" not in result
    assert any("could not load" in str(warning.message) for warning in caught)


def test_instantiation_failure_is_warned_and_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenAdapter(StubApiClientAdapter):
        name = "ep-bad-init"

        def __init__(self) -> None:
            raise RuntimeError("boom")

    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [_make_ep(_BrokenAdapter)])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = load_adapters()

    assert "ep-bad-init" not in result
    assert any("could not instantiate" in str(warning.message) for warning in caught)


# ---------------------------------------------------------------------------
# Whitelist enforcement
# ---------------------------------------------------------------------------


def test_whitelist_excludes_entry_point_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EpAdapter(StubApiClientAdapter):
        name = "ep-filtered"

    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [_make_ep(_EpAdapter)])
    result = load_adapters(whitelist=frozenset({"claude"}))
    assert "ep-filtered" not in result


def test_whitelist_includes_entry_point_adapter_when_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EpAdapter(StubApiClientAdapter):
        name = "ep-allowed"

    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [_make_ep(_EpAdapter)])
    result = load_adapters(whitelist=frozenset({"ep-allowed"}))
    assert "ep-allowed" in result


# ---------------------------------------------------------------------------
# Priority: register() shadows entry-point adapters
# ---------------------------------------------------------------------------


def test_registered_instance_shadows_entry_point_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _EpAdapter(StubApiClientAdapter):
        name = "ep-shadowed"

    class _RegisteredAdapter(StubApiClientAdapter):
        name = "ep-shadowed"

    registered_instance = _RegisteredAdapter()
    monkeypatch.setattr(reg, "_entry_points_for_group", lambda: [_make_ep(_EpAdapter)])
    monkeypatch.setitem(reg._EXTRA, "ep-shadowed", registered_instance)

    result = load_adapters()
    assert result["ep-shadowed"] is registered_instance


# ---------------------------------------------------------------------------
# _describe_ep_source
# ---------------------------------------------------------------------------


def test_describe_ep_source_returns_name_and_version() -> None:
    dist = MagicMock()
    dist.metadata.get.side_effect = lambda key, default="": {
        "Name": "my-pkg",
        "Version": "3.1.4",
    }.get(key, default)
    ep = MagicMock()
    ep.dist = dist
    ep.value = "some.module:SomeClass"
    assert reg._describe_ep_source(ep) == "my-pkg 3.1.4"


def test_describe_ep_source_falls_back_to_value_when_dist_is_none() -> None:
    ep = MagicMock()
    ep.dist = None
    ep.value = "fallback.module:FallbackClass"
    assert reg._describe_ep_source(ep) == "fallback.module:FallbackClass"
