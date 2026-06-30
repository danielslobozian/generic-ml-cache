# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the Jobs HTTP API (detached background executions)."""

from __future__ import annotations

from pydantic import BaseModel


class JobSubmitBody(BaseModel):
    client: str
    model: str
    effort: str = ""
    prompt: str = ""
    context: str = ""
    tags: list[str] = []
    session_id: str | None = None


class JobResponse(BaseModel):
    job_id: str
    state: str
    execution_key: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    error: str | None = None
