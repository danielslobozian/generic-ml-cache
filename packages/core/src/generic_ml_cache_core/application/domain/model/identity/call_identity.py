# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""CallIdentity."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CallIdentity(ABC):
    """The value object that determines an execution's cache key.

    Polymorphic: each execution kind determines its key from different fields
    (a managed call from fingerprints of model/prompt/files; a passthrough call
    from its opaque native args; an API call from its provider and messages). The
    aggregate is addressed by ``generate_key``; every implementation folds its
    kind into the key, so identities of different kinds can never collide.
    """

    @abstractmethod
    def generate_key(self) -> str:
        """Return a stable hex digest that uniquely addresses this call.

        Pure: hashes only the already-in-memory fingerprints. No I/O.
        """

    @property
    @abstractmethod
    def summary_client(self) -> str:
        """The client/provider this identity reports as, for the denormalized
        reporting/query columns (an API identity reports its provider; a gateway
        identity reports its upstream). The identity owns this — a store adapter
        must not re-derive it (the persistence serializer reads it from here too)."""

    @property
    @abstractmethod
    def summary_model(self) -> str:
        """The model this identity reports as for reporting/query, or ``""`` when
        the kind has none (passthrough, gateway)."""
