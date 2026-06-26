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


class EvictionInfo(BaseModel):
    max_size: Optional[int] = None
    max_age: Optional[float] = None
    interval: float
    last_run_at: Optional[float] = None
    last_executions_removed: int = 0
    last_bytes_freed: int = 0


class InfoResponse(BaseModel):
    version: str
    store_root: str
    session_id: Optional[str] = None
    adapters: List[str]
    eviction: EvictionInfo
