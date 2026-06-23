# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for PersistenceDepth."""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth


def test_meter_stores_neither_output_nor_input():
    assert PersistenceDepth.METER.stores_output is False
    assert PersistenceDepth.METER.stores_input is False


def test_cache_stores_output_but_not_input():
    assert PersistenceDepth.CACHE.stores_output is True
    assert PersistenceDepth.CACHE.stores_input is False


def test_dataset_stores_both_output_and_input():
    assert PersistenceDepth.DATASET.stores_output is True
    assert PersistenceDepth.DATASET.stores_input is True


def test_values_are_the_stable_wire_strings():
    assert [depth.value for depth in PersistenceDepth] == ["meter", "cache", "dataset"]
