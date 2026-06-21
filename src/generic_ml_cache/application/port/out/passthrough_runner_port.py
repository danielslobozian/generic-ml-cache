# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""PassthroughRunnerPort."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from generic_ml_cache.application.domain.model.client_run_result import ClientRunResult


class PassthroughRunnerPort(ABC):
    """Outbound port for a passthrough (alias) client launch.

    Distinct from the managed ClientRunnerPort: the args are opaque (gmlcache
    forwards the native tail verbatim), there is no isolated folder and no file
    capture, and the client runs where the caller invoked it. The returned
    ClientRunResult therefore carries stdout/stderr/exit but an empty file list.
    """

    @abstractmethod
    def run(self, client: str, native_args: List[str]) -> ClientRunResult:
        """Launch ``client`` with the verbatim ``native_args`` and return the raw
        result. Raises on unrecoverable launch failure."""
