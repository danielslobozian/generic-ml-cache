# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the Claude gateway (/gateway/claude/v1/messages)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class MessageParam(BaseModel):
    role: str
    content: str


class MessagesRequest(BaseModel):
    model: str
    messages: List[MessageParam]
    max_tokens: int = 8192
    system: Optional[str] = None
    session_id: Optional[str] = None


class ContentBlock(BaseModel):
    type: str = "text"
    text: str


class MessagesResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    content: List[ContentBlock]
    model: str
    stop_reason: str = "end_turn"
    stop_sequence: Optional[str] = None
    usage: Dict[str, Any]
    x_cache_hit: bool = False
