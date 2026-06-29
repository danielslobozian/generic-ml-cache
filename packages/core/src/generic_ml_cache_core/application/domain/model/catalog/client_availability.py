# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientAvailability — the answer to "is this client available?"."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from generic_ml_cache_core.application.domain.model.catalog.adapter_descriptor import (
    AdapterDescriptor,
)


@dataclass(frozen=True)
class ClientAvailability:
    """Whether a client is available in the catalog, and the adapters that serve it."""

    client_name: str
    available: bool
    candidates: Tuple[AdapterDescriptor, ...] = ()
