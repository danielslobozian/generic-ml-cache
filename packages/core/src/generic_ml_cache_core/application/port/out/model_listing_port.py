# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ModelListingPort — independent port for enumerating provider models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from generic_ml_cache_core.application.domain.model.model_info import ModelInfo


class ModelListingPort(ABC):
    """Optional capability port: enumerate the models a provider exposes.

    Deliberately separate from ApiClientPort (Interface Segregation): an API
    adapter that can run prompts but has no model-listing endpoint does NOT
    implement this port. Discovery code checks isinstance(adapter, ModelListingPort)
    rather than calling a defaulting method on the runner port.

    Carries ``name`` so a list of ModelListingPort instances can be indexed by
    adapter identity without casting to the concrete type — same pattern as
    MlRunnerPort.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique adapter name, shared with MlRunnerPort (e.g. ``"anthropic"``)."""

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """Return all models this provider exposes.

        Raises on a transport failure so the caller can surface the reason.
        Returns an empty list if the endpoint is reachable but lists nothing.
        """
