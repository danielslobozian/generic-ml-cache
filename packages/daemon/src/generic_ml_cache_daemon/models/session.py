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


class SessionStatsResponse(BaseModel):
    session_id: str
    tags: List[str]
    spec: Optional[SpecBody] = None
    calls: int
    hits: int
    hit_rate: float


class TagBody(BaseModel):
    tag: str


class SessionListResponse(BaseModel):
    session_ids: List[str]
