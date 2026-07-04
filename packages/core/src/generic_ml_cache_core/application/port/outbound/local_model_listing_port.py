# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""LocalModelListingPort — the model-listing role of a local CLI client (W24).

One of the four role ports the fat ``LocalClientPort`` was split into: enumerating a
client's models is a distinct capability a managed/passthrough run never needs. Not
every client lists models — ``models_argv`` returns ``None`` when unsupported, and
``parse_model_list`` is then never called.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from generic_ml_cache_core.application.domain.model.model_info import ModelInfo


class LocalModelListingPort(ABC):
    """Enumerate the models a local CLI client offers."""

    @abstractmethod
    def models_argv(self, executable: str) -> list[str] | None:
        """Argv to enumerate available models, or ``None`` if unsupported."""

    @abstractmethod
    def parse_model_list(self, stdout: str) -> list[ModelInfo]:
        """Structure the client's raw model-list output into ``ModelInfo`` objects.
        Only called when :meth:`models_argv` is non-``None``."""
