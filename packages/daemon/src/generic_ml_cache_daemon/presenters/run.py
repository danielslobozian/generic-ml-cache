# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the /run endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class RunBody(BaseModel):
    client: str
    model: str
    effort: str = ""
    prompt: str = ""
    context: str = ""
    tags: list[str] = []
    session_id: str | None = None


class RunResponse(BaseModel):
    execution_key: str
    state: str
    cache_hit: bool
    stdout: str | None = None
    stderr: str | None = None
