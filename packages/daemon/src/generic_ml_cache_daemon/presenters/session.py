# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the Sessions HTTP API."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class SpecBody(BaseModel):
    client: str
    model: str
    effort: str


class SessionCreateBody(BaseModel):
    tags: List[str] = []
    spec: Optional[SpecBody] = None


class SessionResponse(BaseModel):
    session_id: str
    tags: List[str]
    spec: Optional[SpecBody] = None


class ModelUsageBody(BaseModel):
    client: str
    model: str
    spent_input: int
    spent_output: int
    cache_read_tokens: int
    cache_write_tokens: int
    reasoning_tokens: int
    saved_tokens: int
    executions: int
    hits: int


class SessionStatsResponse(BaseModel):
    session_id: str
    tags: List[str]
    spec: Optional[SpecBody] = None
    calls: int
    hits: int
    hit_rate: float
    by_model: List[ModelUsageBody] = []


class TagBody(BaseModel):
    tag: str


class SessionListResponse(BaseModel):
    session_ids: List[str]
