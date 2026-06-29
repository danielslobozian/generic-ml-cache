# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the Claude gateway (/gateway/claude/v1/messages)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict


class MessageParam(BaseModel):
    role: str
    # The Anthropic API allows content to be either a plain string or a list of
    # typed content blocks (text, image, tool_use, tool_result …).
    content: Union[str, List[Dict[str, Any]]]


class MessagesRequest(BaseModel):
    # Keep unknown fields (`temperature`, `top_p`, `tools`, `stop_sequences`,
    # `metadata`, `stream`, `thinking`, …) so the gateway forwards them upstream
    # verbatim and keys them — a transparent proxy must never silently drop a field
    # the caller sent. The named fields below are validated; everything else passes
    # through via ``extra="allow"``.
    model_config = ConfigDict(extra="allow")

    model: str
    messages: List[MessageParam]
    max_tokens: int = 8192
    system: Optional[Union[str, List[Dict[str, Any]]]] = None
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
