# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the /run endpoint."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class RunBody(BaseModel):
    client: str
    model: str
    effort: str = ""
    prompt: str = ""
    context: str = ""
    tags: List[str] = []
    session_id: Optional[str] = None


class RunResponse(BaseModel):
    execution_key: str
    state: str
    cache_hit: bool
    stdout: Optional[str] = None
    stderr: Optional[str] = None
