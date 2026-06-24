# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for GeminiThinkingConfig and GeminiEffortType."""

from __future__ import annotations

import pytest

from generic_ml_cache_core.adapter.out.api._gemini_thinking import (
    GeminiEffortType,
    GeminiThinkingConfig,
    _effort_type_for_model,
)


# ---------------------------------------------------------------------------
# Effort type detection — 2.5 (budget) vs 3.x (level)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model", [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash-preview",
    "gemini-2.5-flash-image",
    "gemini-2.5-computer-use-preview",
    "gemini-robotics-er-1.5-preview",
    "gemini-robotics-er-1.6-preview",
])
def test_budget_models_return_budget_type(model):
    assert _effort_type_for_model(model) is GeminiEffortType.BUDGET


@pytest.mark.parametrize("model", [
    "gemini-2.5-pro-001",
    "gemini-2.5-flash-001",
    "gemini-2.5-flash-lite-001",
    "gemini-2.5-computer-use-preview-10-2025",
    "gemini-robotics-er-1.6-preview-v2",
])
def test_versioned_budget_models_return_budget_type(model):
    assert _effort_type_for_model(model) is GeminiEffortType.BUDGET


@pytest.mark.parametrize("model", [
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-pro-latest",
])
def test_level_models_return_level_type(model):
    assert _effort_type_for_model(model) is GeminiEffortType.LEVEL


def test_models_prefix_is_stripped():
    assert _effort_type_for_model("models/gemini-2.5-flash") is GeminiEffortType.BUDGET
    assert _effort_type_for_model("models/gemini-3.5-flash") is GeminiEffortType.LEVEL


def test_unknown_model_defaults_to_level():
    assert _effort_type_for_model("gemini-future-model") is GeminiEffortType.LEVEL


# ---------------------------------------------------------------------------
# GeminiThinkingConfig.from_effort — level models
# ---------------------------------------------------------------------------


def test_level_model_low_effort_sets_thinking_level():
    cfg = GeminiThinkingConfig.from_effort("low", "gemini-3.5-flash")
    assert cfg.effort_type is GeminiEffortType.LEVEL
    assert cfg.level == "low"
    assert not cfg.is_budget


def test_level_model_high_effort_sets_thinking_level():
    cfg = GeminiThinkingConfig.from_effort("high", "gemini-3.1-pro-preview")
    assert cfg.level == "high"


def test_level_model_minimal_effort_forwarded_verbatim():
    cfg = GeminiThinkingConfig.from_effort("minimal", "gemini-3-flash-preview")
    assert cfg.level == "minimal"


def test_level_model_to_dict_returns_thinking_level_key():
    cfg = GeminiThinkingConfig.from_effort("medium", "gemini-3.5-flash")
    assert cfg.to_dict() == {"thinkingLevel": "medium"}


# ---------------------------------------------------------------------------
# GeminiThinkingConfig.from_effort — budget models
# ---------------------------------------------------------------------------


def test_budget_model_low_maps_to_1024():
    cfg = GeminiThinkingConfig.from_effort("low", "gemini-2.5-flash")
    assert cfg.effort_type is GeminiEffortType.BUDGET
    assert cfg.budget == 1024
    assert cfg.is_budget


def test_budget_model_medium_maps_to_8192():
    cfg = GeminiThinkingConfig.from_effort("medium", "gemini-2.5-flash")
    assert cfg.budget == 8192


def test_budget_model_high_maps_to_24576():
    cfg = GeminiThinkingConfig.from_effort("high", "gemini-2.5-pro")
    assert cfg.budget == 24576


def test_budget_model_digit_string_is_parsed_as_raw_token_count():
    cfg = GeminiThinkingConfig.from_effort("2048", "gemini-2.5-flash")
    assert cfg.budget == 2048


def test_budget_model_to_dict_returns_thinking_budget_key():
    cfg = GeminiThinkingConfig.from_effort("low", "gemini-2.5-flash")
    assert cfg.to_dict() == {"thinkingBudget": 1024}


def test_budget_model_unknown_string_falls_back_to_medium():
    cfg = GeminiThinkingConfig.from_effort("ultra", "gemini-2.5-flash")
    assert cfg.budget == 8192


def test_budget_model_versioned_still_uses_budget():
    cfg = GeminiThinkingConfig.from_effort("high", "gemini-2.5-flash-001")
    assert cfg.is_budget
    assert cfg.budget == 24576


# ---------------------------------------------------------------------------
# is_budget property
# ---------------------------------------------------------------------------


def test_is_budget_false_for_level_type():
    cfg = GeminiThinkingConfig.from_effort("low", "gemini-3.5-flash")
    assert not cfg.is_budget


def test_is_budget_true_for_budget_type():
    cfg = GeminiThinkingConfig.from_effort("low", "gemini-2.5-flash")
    assert cfg.is_budget


# ---------------------------------------------------------------------------
# Integration: adapter _build_body routes correctly
# ---------------------------------------------------------------------------


def test_adapter_build_body_uses_thinking_level_for_3x(monkeypatch):
    from generic_ml_cache_core.adapter.out.api.gemini_direct_adapter import GeminiDirectAdapter
    from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest

    adapter = GeminiDirectAdapter(api_key="test")
    body = adapter._build_body(MlRequest(model="gemini-3.5-flash", effort="high", context="", prompt="hi"))
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"}


def test_adapter_build_body_uses_thinking_budget_for_25(monkeypatch):
    from generic_ml_cache_core.adapter.out.api.gemini_direct_adapter import GeminiDirectAdapter
    from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest

    adapter = GeminiDirectAdapter(api_key="test")
    body = adapter._build_body(MlRequest(model="gemini-2.5-flash", effort="low", context="", prompt="hi"))
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 1024}


def test_adapter_build_body_no_effort_omits_generation_config():
    from generic_ml_cache_core.adapter.out.api.gemini_direct_adapter import GeminiDirectAdapter
    from generic_ml_cache_core.application.domain.model.run.ml_request import MlRequest

    adapter = GeminiDirectAdapter(api_key="test")
    body = adapter._build_body(MlRequest(model="gemini-3.5-flash", effort="", context="", prompt="hi"))
    assert "generationConfig" not in body
