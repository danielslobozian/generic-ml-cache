# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the Executions HTTP API and global stats/purge."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ExecutionSummaryResponse(BaseModel):
    execution_key: str
    kind: str
    client: str
    model: str


class ExecutionListResponse(BaseModel):
    executions: list[ExecutionSummaryResponse]
    total: int


class GlobalStatsResponse(BaseModel):
    executions: int
    event_counts: dict[str, int]


class PurgeByAll(BaseModel):
    by: Literal["all"]


class PurgeByKey(BaseModel):
    by: Literal["key"]
    target: str


class PurgeByTag(BaseModel):
    by: Literal["tag"]
    target: str


class PurgeBySession(BaseModel):
    by: Literal["session"]
    target: str


class PurgeBySessionTag(BaseModel):
    by: Literal["session_tag"]
    target: str


PurgeBody = PurgeByAll | PurgeByKey | PurgeByTag | PurgeBySession | PurgeBySessionTag


class PurgeResponse(BaseModel):
    executions_removed: int
    bytes_freed: int
    blobs_removed: int
