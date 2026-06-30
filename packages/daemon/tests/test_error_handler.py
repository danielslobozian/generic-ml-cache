# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests: CacheError exception handler maps error codes to HTTP statuses."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from generic_ml_cache_core.common.errors import (
    ArtifactBlobMissing,
    CacheError,
    CacheMiss,
    EncryptionStateError,
    EncryptionTokenRequired,
    StoreLocked,
    UnknownClient,
    WrongEncryptionToken,
)
from starlette.testclient import TestClient


def _client_raising(exc: Exception, tmp_path: Path) -> TestClient:
    """Build a TestClient whose run_ml.execute always raises *exc*."""
    from generic_ml_cache_daemon.app import create_app

    app = create_app(tmp_path)
    app.state.wired.run_ml.execute = MagicMock(side_effect=exc)
    return TestClient(app, raise_server_exceptions=False)


def _post_run(tc: TestClient):
    return tc.post(
        "/run",
        json={"client": "claude", "model": "claude-3-5-sonnet-20241022", "prompt": "hello"},
    )


@pytest.mark.parametrize(
    "exc, expected_status, expected_code",
    [
        (CacheMiss("no match"), 404, "cache.miss"),
        (UnknownClient("xyz"), 400, "adapter.unknown"),
        (StoreLocked("held"), 409, "store.locked"),
        (EncryptionStateError("already encrypted"), 409, "crypto.state_error"),
        (WrongEncryptionToken("bad token"), 401, "crypto.wrong_token"),
        (EncryptionTokenRequired("need token"), 401, "crypto.token_required"),
        (ArtifactBlobMissing("blob gone"), 404, "store.blob_missing"),
        (CacheError("unexpected"), 500, "cache.error"),
    ],
)
def test_cache_error_handler(
    tmp_path: Path, exc: CacheError, expected_status: int, expected_code: str
) -> None:
    tc = _client_raising(exc, tmp_path)
    response = _post_run(tc)
    assert response.status_code == expected_status
    body = response.json()
    assert body["code"] == expected_code
    assert "detail" in body


def test_unknown_client_from_build_command(client: TestClient) -> None:
    """UnknownClient raised in _build_command is caught by the global handler."""
    response = client.post(
        "/run",
        json={"client": "no_such_adapter_xyz", "model": "m", "prompt": "hi"},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "adapter.unknown"
    assert "detail" in body
