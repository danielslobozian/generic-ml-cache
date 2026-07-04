# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""FilesystemFileFingerprint: read a file and fingerprint it at the edge."""

from __future__ import annotations

from pathlib import Path

from generic_ml_cache_core.application.port.outbound.file_fingerprint_port import (
    FileFingerprintPort,
)
from generic_ml_cache_core.common.checksum import file_content_fingerprint
from generic_ml_cache_core.common.errors import InputFileError


class FilesystemFileFingerprint(FileFingerprintPort):
    """Fingerprint a declared input file off the local filesystem.

    Reads the bytes and applies the imported core rule, returning only the
    checksum. The content stays inside this adapter — it never crosses back to
    the use case. The rule is imported from the core, never reimplemented here.
    """

    def fingerprint(self, path: str) -> str:
        file_path = Path(path)
        if not file_path.is_file():
            raise InputFileError(f"input file not found: {path}")
        try:
            content = file_path.read_bytes()
        except OSError as error:
            raise InputFileError(f"cannot read input file {path}: {error}") from error
        return file_content_fingerprint(content)
