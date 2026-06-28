# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests: CacheError subclasses carry stable, machine-readable code attributes."""

from __future__ import annotations

import pytest

from generic_ml_cache_core.common.errors import (
    ArtifactBlobMissing,
    CacheError,
    CacheMiss,
    ClientNotFound,
    CommandLineTooLong,
    ConfigError,
    EncryptionStateError,
    EncryptionTokenRequired,
    InputFileError,
    RunInterrupted,
    StoreLocked,
    UnknownClient,
    WrongEncryptionToken,
)


def test_base_cache_error_has_fallback_code() -> None:
    assert CacheError.code == "cache.error"


@pytest.mark.parametrize(
    "cls, expected",
    [
        (CacheMiss, "cache.miss"),
        (UnknownClient, "adapter.unknown"),
        (ConfigError, "config.invalid"),
        (ClientNotFound, "adapter.not_found"),
        (CommandLineTooLong, "adapter.command_too_long"),
        (InputFileError, "input.file_error"),
        (ArtifactBlobMissing, "store.blob_missing"),
        (WrongEncryptionToken, "crypto.wrong_token"),
        (EncryptionTokenRequired, "crypto.token_required"),
        (EncryptionStateError, "crypto.state_error"),
        (StoreLocked, "store.locked"),
    ],
)
def test_concrete_error_code(cls, expected: str) -> None:
    assert cls.code == expected


def test_code_accessible_on_raised_instance() -> None:
    exc = CacheMiss("no cached execution found")
    assert exc.code == "cache.miss"


def test_code_accessible_on_base_instance() -> None:
    exc = CacheError("something went wrong")
    assert exc.code == "cache.error"


def test_run_interrupted_has_no_code() -> None:
    assert not hasattr(RunInterrupted, "code")
