# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Cacheability rule: a pure domain rule shared by every front door."""

from __future__ import annotations

from typing import Sequence


def is_call_uncacheable(allow_paths: Sequence[str], scan_trust: bool) -> bool:
    """Whether a call is non-cacheable because it declares allow-path folders.

    Their contents are unbounded and cannot be fingerprinted, so the cache cannot
    tell when they change — the call is therefore non-cacheable. ``scan_trust`` is
    the caller's explicit override (asserting the folders are stable). This is the
    single source of the rule, so a probe and a run can never disagree about
    whether a given call is cacheable.
    """
    return bool(allow_paths) and not scan_trust
