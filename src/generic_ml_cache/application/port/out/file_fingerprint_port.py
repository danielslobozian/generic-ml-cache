# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FileFingerprintPort."""

from __future__ import annotations

from abc import ABC, abstractmethod


class FileFingerprintPort(ABC):
    """Outbound port for fingerprinting a declared input file at the edge.

    The adapter reads the file and applies the imported core rule, returning
    ONLY the checksum. The file content never crosses back into the use case
    or the domain — the engine fingerprints a file without ever holding its
    content. The rule is owned by the core (common/checksum), never by the
    adapter, so two adapters can never derive different keys for the same file.
    """

    @abstractmethod
    def fingerprint(self, path: str) -> str:
        """Return the content fingerprint of the file at ``path``.

        Raises if the path does not point to a readable regular file.
        """
