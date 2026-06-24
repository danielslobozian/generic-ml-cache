# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for api_discover.list_api_models and the api_registry."""

from __future__ import annotations

from typing import List

import pytest

from generic_ml_cache_core.adapter.out.api.api_discover import list_api_models
from generic_ml_cache_core.adapter.out.api.api_registry import (
    get_api_adapter,
    register_api_adapter,
    registered_api_names,
)
from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.run.client_run_result import ClientRunResult
from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest
from generic_ml_cache_core.application.port.out.api_client_port import ApiClientPort
from generic_ml_cache_core.application.port.out.model_listing_port import ModelListingPort
from generic_ml_cache_core.common.errors import UnknownClient


# ---------------------------------------------------------------------------
# Fake adapters for test control
# ---------------------------------------------------------------------------


class _ListingAdapter(ApiClientPort, ModelListingPort):
    name = "_listing"

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

    def run(self, request: MlRequest) -> ClientRunResult:
        raise NotImplementedError


class _FailingListAdapter(ApiClientPort, ModelListingPort):
    name = "_fail-listing"

    def run(self, request: MlRequest) -> ClientRunResult:
        raise NotImplementedError

    def list_models(self) -> List[ModelInfo]:
        raise RuntimeError("connection refused")


# ---------------------------------------------------------------------------
# api_registry
# ---------------------------------------------------------------------------


def test_register_and_get_api_adapter():
    register_api_adapter("_test_listing", lambda k: _ListingAdapter())
    adapter = get_api_adapter("_test_listing")
    assert isinstance(adapter, _ListingAdapter)


def test_get_unknown_adapter_raises_unknown_client():
    with pytest.raises(UnknownClient, match="unknown API provider"):
        get_api_adapter("__no_such_provider__")


def test_registered_api_names_includes_registered():
    register_api_adapter("_test_z", lambda k: _NonListingAdapter())
    assert "_test_z" in registered_api_names()


def test_gemini_is_registered_by_default():
    # The api package __init__ eagerly registers "gemini".
    import generic_ml_cache_core.adapter.out.api  # noqa: F401 — triggers registration

    assert "gemini" in registered_api_names()


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
    register_api_adapter("_test_api_list", lambda k: _ListingAdapter())
    ml = list_api_models("_test_api_list")
    assert ml.present is True
    assert ml.supported is True
    assert [m.id for m in ml.models] == ["model-a", "model-b"]


def test_listing_adapter_passes_api_key_to_factory():
    received = {}

    def factory(api_key):
        received["key"] = api_key
        return _ListingAdapter()

    register_api_adapter("_test_api_key", factory)
    list_api_models("_test_api_key", api_key="my-secret")
    assert received["key"] == "my-secret"


# ---------------------------------------------------------------------------
# list_api_models — provider with no listing support
# ---------------------------------------------------------------------------


def test_non_listing_adapter_returns_supported_false():
    register_api_adapter("_test_no_list", lambda k: _NonListingAdapter())
    ml = list_api_models("_test_no_list")
    assert ml.present is True
    assert ml.supported is False
    assert ml.models is None


# ---------------------------------------------------------------------------
# list_api_models — transport failure
# ---------------------------------------------------------------------------


def test_failing_list_adapter_returns_reason():
    register_api_adapter("_test_fail_list", lambda k: _FailingListAdapter())
    ml = list_api_models("_test_fail_list")
    assert ml.present is True
    assert ml.supported is True  # provider is there; listing just failed
    assert ml.models is None
    assert "connection refused" in (ml.reason or "")


# ---------------------------------------------------------------------------
# port segregation contract
# ---------------------------------------------------------------------------


def test_listing_adapter_implements_model_listing_port():
    assert isinstance(_ListingAdapter(), ModelListingPort)


def test_non_listing_adapter_does_not_implement_model_listing_port():
    assert not isinstance(_NonListingAdapter(), ModelListingPort)
