# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic response models for /health, /ready, and /info."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    detail: str | None = None


class EvictionInfo(BaseModel):
    max_size: int | None = None
    max_age: float | None = None
    interval: float
    last_run_at: float | None = None
    last_executions_removed: int = 0
    last_bytes_freed: int = 0


class InfoResponse(BaseModel):
    version: str
    store_root: str
    session_id: str | None = None
    adapters: list[str]
    eviction: EvictionInfo
