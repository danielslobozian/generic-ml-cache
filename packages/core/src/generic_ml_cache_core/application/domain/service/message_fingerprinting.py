# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Fingerprinting of an API message list — a pure domain rule."""

from __future__ import annotations

from typing import Dict, Sequence

from generic_ml_cache_core.application.domain.model.run.message import Message
from generic_ml_cache_core.common.checksum import checksum_input_data


def fingerprint_messages(messages: Sequence[Message]) -> str:
    """Fingerprint an ordered message list into the key.

    The messages may carry the user's full context (sensitive), so only their
    digest is ever keyed or stored — never the raw content. Order is significant
    and preserved by the positional keys; identical message lists fingerprint
    identically.
    """
    data: Dict[str, str] = {}
    for index, message in enumerate(messages):
        data[f"{index}:role"] = message.role
        data[f"{index}:content"] = message.content
    return checksum_input_data(data)
