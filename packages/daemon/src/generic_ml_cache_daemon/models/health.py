# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic response models for /health, /ready, and /info."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    detail: Optional[str] = None


class InfoResponse(BaseModel):
    version: str
    store_root: str
    session_id: Optional[str] = None
    adapters: List[str]
