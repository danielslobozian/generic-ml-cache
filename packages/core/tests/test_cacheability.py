# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for the cacheability domain rule."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.service.cacheability import is_call_uncacheable


def test_plain_call_is_cacheable():
    assert is_call_uncacheable([], False) is False


def test_allow_paths_make_a_call_uncacheable():
    assert is_call_uncacheable(["/workspace"], False) is True


def test_scan_trust_overrides_allow_paths():
    assert is_call_uncacheable(["/workspace"], True) is False


def test_scan_trust_without_allow_paths_is_still_cacheable():
    assert is_call_uncacheable([], True) is False
