# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""End-to-end: a managed run against an encrypted store (via build_use_cases)."""

from __future__ import annotations

import sqlite3

import pytest
from generic_ml_cache_core.application.port.inbound.execution_query.find_current_execution_command import (
    FindCurrentExecutionCommand,
)

pytest.importorskip("cryptography")

from generic_ml_cache_adapters.adapter.out.crypto.aesgcm_cipher import AesGcmCipher  # noqa: E402
from generic_ml_cache_adapters.adapter.out.crypto.filesystem_encryption_manifest_store import (  # noqa: E402
    FilesystemEncryptionManifestStore,
)
from generic_ml_cache_core.application.domain.model.execution.artifact import (  # noqa: E402
    ArtifactType,
)
from generic_ml_cache_core.application.domain.model.execution.execution_kind import (  # noqa: E402
    ExecutionKind,
)
from generic_ml_cache_core.application.domain.model.execution.execution_state import (  # noqa: E402
    ExecutionState,
)
from generic_ml_cache_core.application.port.inbound.run_ml_execution_command import (  # noqa: E402
    RunMlExecutionCommand,
)
from generic_ml_cache_core.common.errors import (  # noqa: E402
    EncryptionTokenRequired,
    WrongEncryptionToken,
)

from generic_ml_cache_cli._compose import build_use_cases  # noqa: E402

_MARKER = "ENCRYPTME-distinctive-123"


def _encrypt_store(store_root, token):
    manifest, _ = AesGcmCipher().create_envelope(token)
    FilesystemEncryptionManifestStore(store_root).save(manifest)


def _command():
    return RunMlExecutionCommand(
        execution_kind=ExecutionKind.LOCAL_MANAGED,
        client="fake",
        model="m1",
        effort="high",
        context="",
        prompt=f"STDOUT {_MARKER}",
    )


def _db_factory(store):
    db_path = store / "executions.sqlite3"

    def _connect():
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(str(db_path))

    return _connect


def _blob_bytes(store_root):
    return b"".join(p.read_bytes() for p in (store_root / "blobs").rglob("*") if p.is_file())


def test_encrypted_run_stores_ciphertext_and_replays_with_token(tmp_path):
    store = tmp_path / "store"
    token = AesGcmCipher().generate_token()
    _encrypt_store(store, token)

    execution = build_use_cases(
        _db_factory(store), store, encryption_token=token, client="fake"
    ).run_ml.execute(_command())
    assert execution.execution_state is ExecutionState.SUCCESS

    # the marker must NOT appear in the persisted blobs — they are ciphertext
    assert _MARKER.encode() not in _blob_bytes(store)

    # replay (a cache hit) with the token decrypts the output correctly
    served = build_use_cases(
        _db_factory(store), store, encryption_token=token, client="fake"
    ).run_ml.execute(_command())
    stdout = next(a.content for a in served.artifacts if a.artifact_type is ArtifactType.STDOUT)
    assert _MARKER.encode() in stdout


def test_public_store_keeps_plaintext_and_ignores_a_token(tmp_path):
    store = tmp_path / "store"  # no manifest -> public
    execution = build_use_cases(
        _db_factory(store), store, encryption_token="ignored", client="fake"
    ).run_ml.execute(_command())
    assert execution.execution_state is ExecutionState.SUCCESS
    assert _MARKER.encode() in _blob_bytes(store)  # plaintext on disk


def test_encrypted_store_without_token_blocks_content_but_not_metadata(tmp_path):
    store = tmp_path / "store"
    token = AesGcmCipher().generate_token()
    _encrypt_store(store, token)
    recorded = build_use_cases(
        _db_factory(store), store, encryption_token=token, client="fake"
    ).run_ml.execute(_command())
    key = recorded.call_identity.generate_key()

    wired = build_use_cases(_db_factory(store), store)  # no token — metadata-only, no client needed
    # metadata is still readable (it is not encrypted) ...
    assert wired.execution_query.find_current(FindCurrentExecutionCommand(key)) is not None
    # ... but serving the hit must hydrate the blob, which needs the token.
    with pytest.raises(EncryptionTokenRequired):
        build_use_cases(_db_factory(store), store, client="fake").run_ml.execute(_command())


def test_wrong_token_is_rejected_when_opening_the_store(tmp_path):
    store = tmp_path / "store"
    _encrypt_store(store, AesGcmCipher().generate_token())
    with pytest.raises(WrongEncryptionToken):
        build_use_cases(_db_factory(store), store, encryption_token=AesGcmCipher().generate_token())
