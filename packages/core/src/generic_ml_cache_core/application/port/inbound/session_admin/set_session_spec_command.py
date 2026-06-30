# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""SetSessionSpecCommand."""

from __future__ import annotations

from dataclasses import dataclass

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec


@dataclass(frozen=True)
class SetSessionSpecCommand:
    """Attach (or replace) the execution spec for ``session_id``."""

    session_id: str
    spec: SessionSpec
