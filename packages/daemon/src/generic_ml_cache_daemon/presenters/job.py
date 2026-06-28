# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the Jobs HTTP API (detached background executions)."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class JobSubmitBody(BaseModel):
    client: str
    model: str
    effort: str = ""
    prompt: str = ""
    context: str = ""
    tags: List[str] = []
    session_id: Optional[str] = None


class JobResponse(BaseModel):
    job_id: str
    state: str
    execution_key: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    error: Optional[str] = None
