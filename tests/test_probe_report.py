# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for ProbeReport."""

from __future__ import annotations

import pytest

from generic_ml_cache.application.domain.model.probe_report import ProbeReport
from generic_ml_cache.application.domain.model.probe_status import ProbeStatus


def test_miss_report_has_a_key_and_no_execution():
    report = ProbeReport(status=ProbeStatus.MISS, execution_key="abc")
    assert report.status is ProbeStatus.MISS
    assert report.execution_key == "abc"
    assert report.execution is None


def test_non_cacheable_report_carries_the_key():
    report = ProbeReport(status=ProbeStatus.NON_CACHEABLE, execution_key="def")
    assert report.status is ProbeStatus.NON_CACHEABLE
    assert report.execution_key == "def"
    assert report.execution is None


def test_is_frozen():
    report = ProbeReport(status=ProbeStatus.MISS, execution_key="abc")
    with pytest.raises(Exception):
        report.status = ProbeStatus.HIT  # type: ignore[misc]
