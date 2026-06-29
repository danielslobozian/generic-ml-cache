# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for api_discover.list_api_models and the unified adapter registry."""

from __future__ import annotations

from typing import List

import pytest

from generic_ml_cache_adapters.adapter.out.api.api_discover import list_api_models
from generic_ml_cache_adapters.discovery.composition import get_adapter, registered_names
from generic_ml_cache_adapters.discovery.in_memory_adapter_registry import register
from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.domain.model.catalog.client_capability import (
    ClientCapability,
)
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort
from generic_ml_cache_core.application.port.out.model_listing_port import ModelListingPort
from generic_ml_cache_core.common.errors import UnknownClient
from generic_ml_cache_adapters.discovery.descriptors import api_descriptor

_RUN = ClientCapability.RUN
_LIST = ClientCapability.LIST_MODELS


# ---------------------------------------------------------------------------
# Fake adapters for test control
# ---------------------------------------------------------------------------


class _ListingAdapter(ApiClientPort, ModelListingPort):
    name = "_listing"

    @classmethod
    def descriptor(cls):
        return api_descriptor("_listing", {_RUN, _LIST}, "Listing")

    def run(self, request: MlRequest) -> ClientRunResult:
        raise NotImplementedError

    def list_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(id="model-a", name="Model A"),
            ModelInfo(id="model-b", name="Model B"),
        ]


class _NonListingAdapter(ApiClientPort):
    """API adapter with no model-listing capability (does not implement ModelListingPort)."""

    name = "_non-listing"

    @classmethod
    def descriptor(cls):
        return api_descriptor("_non-listing", {_RUN}, "NonListing")

    def run(self, request: MlRequest) -> ClientRunResult:
        raise NotImplementedError


class _FailingListAdapter(ApiClientPort, ModelListingPort):
    name = "_fail-listing"

    @classmethod
    def descriptor(cls):
        return api_descriptor("_fail-listing", {_RUN, _LIST}, "Failing")

    def run(self, request: MlRequest) -> ClientRunResult:
        raise NotImplementedError

    def list_models(self) -> List[ModelInfo]:
        raise RuntimeError("connection refused")


# ---------------------------------------------------------------------------
# unified registry
# ---------------------------------------------------------------------------


def test_register_and_get_adapter():
    register(_ListingAdapter)
    adapter = get_adapter("_listing")
    assert isinstance(adapter, _ListingAdapter)


def test_get_unknown_adapter_raises_unknown_client():
    with pytest.raises(UnknownClient, match="unknown adapter"):
        get_adapter("__no_such_provider__")


def test_registered_names_includes_registered():
    register(_NonListingAdapter)
    assert "_non-listing" in registered_names()


def test_builtins_registered_via_scanner():
    # The scanner discovers @adapter-decorated classes automatically.
    assert "gemini" in registered_names()
    assert "anthropic" in registered_names()
    assert "openai" in registered_names()


# ---------------------------------------------------------------------------
# list_api_models — unknown provider
# ---------------------------------------------------------------------------


def test_unknown_provider_returns_not_present():
    ml = list_api_models("__no_such_provider__")
    assert ml.present is False
    assert ml.supported is False
    assert ml.models is None
    assert "unknown" in (ml.reason or "").lower()


# ---------------------------------------------------------------------------
# list_api_models — provider with listing support
# ---------------------------------------------------------------------------


def test_listing_adapter_returns_models():
    register(_ListingAdapter)
    ml = list_api_models("_listing")
    assert ml.present is True
    assert ml.supported is True
    assert [m.id for m in ml.models] == ["model-a", "model-b"]


# ---------------------------------------------------------------------------
# list_api_models — provider with no listing support
# ---------------------------------------------------------------------------


def test_non_listing_adapter_returns_supported_false():
    register(_NonListingAdapter)
    ml = list_api_models("_non-listing")
    assert ml.present is True
    assert ml.supported is False
    assert ml.models is None


# ---------------------------------------------------------------------------
# list_api_models — transport failure
# ---------------------------------------------------------------------------


def test_failing_list_adapter_returns_reason():
    register(_FailingListAdapter)
    ml = list_api_models("_fail-listing")
    assert ml.present is True
    assert ml.supported is True
    assert ml.models is None
    assert "connection refused" in (ml.reason or "")


# ---------------------------------------------------------------------------
# port segregation contract
# ---------------------------------------------------------------------------


def test_listing_adapter_implements_model_listing_port():
    assert isinstance(_ListingAdapter(), ModelListingPort)


def test_non_listing_adapter_does_not_implement_model_listing_port():
    assert not isinstance(_NonListingAdapter(), ModelListingPort)


# ---------------------------------------------------------------------------
# whitelist filtering (0.16.0)
# ---------------------------------------------------------------------------


def test_list_api_models_whitelist_excludes_disabled_provider():
    register(_ListingAdapter)
    ml = list_api_models("_listing", whitelist=frozenset({"other"}))
    assert ml.present is False
    assert "unknown adapter" in (ml.reason or "").lower()


def test_list_api_models_whitelist_allows_included_provider():
    register(_ListingAdapter)
    ml = list_api_models("_listing", whitelist=frozenset({"_listing"}))
    assert ml.present is True
    assert ml.supported is True


def test_list_api_models_none_whitelist_allows_all():
    register(_ListingAdapter)
    ml = list_api_models("_listing", whitelist=None)
    assert ml.present is True
