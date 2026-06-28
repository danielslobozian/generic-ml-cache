# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import dataclasses
import pytest

from generic_ml_cache_core.application.domain.model.client_status import ClientStatus
from generic_ml_cache_core.application.domain.model.encryption.encryption_manifest import (
    EncryptionManifest,
)
from generic_ml_cache_core.application.domain.model.encryption.encryption_state import (
    EncryptionState,
)
from generic_ml_cache_core.application.domain.model.model_info import ModelInfo
from generic_ml_cache_core.application.domain.model.model_listing import ModelListing


class TestClientStatus:
    def test_required_fields_set_correctly(self):
        status = ClientStatus(name="claude", present=True)
        assert status.name == "claude"
        assert status.present is True

    def test_optional_fields_default_to_none(self):
        status = ClientStatus(name="codex", present=False)
        assert status.executable is None
        assert status.version is None
        assert status.detail is None

    def test_optional_fields_can_be_set(self):
        status = ClientStatus(
            name="claude",
            present=True,
            executable="/usr/bin/claude",
            version="1.2.3",
            detail="found on PATH",
        )
        assert status.executable == "/usr/bin/claude"
        assert status.version == "1.2.3"
        assert status.detail == "found on PATH"

    def test_present_false_is_valid(self):
        status = ClientStatus(name="unknown", present=False, detail="not installed")
        assert status.present is False
        assert status.detail == "not installed"


class TestModelListing:
    def test_required_fields_set_correctly(self):
        listing = ModelListing(name="claude", present=True, supported=True)
        assert listing.name == "claude"
        assert listing.present is True
        assert listing.supported is True

    def test_models_and_reason_default_to_none(self):
        listing = ModelListing(name="claude", present=True, supported=True)
        assert listing.models is None
        assert listing.reason is None

    def test_present_false_with_absent_models_is_valid(self):
        listing = ModelListing(name="ghost", present=False, supported=False)
        assert listing.present is False
        assert listing.models is None

    def test_supported_false_with_reason(self):
        listing = ModelListing(name="codex", present=True, supported=False, reason="no list api")
        assert listing.supported is False
        assert listing.reason == "no list api"

    def test_supported_true_with_models_list(self):
        models = [ModelInfo(id="m1", name="Model 1"), ModelInfo(id="m2", name="Model 2")]
        listing = ModelListing(name="claude", present=True, supported=True, models=models)
        assert len(listing.models) == 2
        assert listing.models[0].id == "m1"


class TestEncryptionManifest:
    def test_fields_stored_correctly(self):
        manifest = EncryptionManifest(kdf_salt=b"salt", wrapped_data_key=b"key")
        assert manifest.kdf_salt == b"salt"
        assert manifest.wrapped_data_key == b"key"

    def test_version_defaults_to_1(self):
        manifest = EncryptionManifest(kdf_salt=b"s", wrapped_data_key=b"k")
        assert manifest.version == 1

    def test_version_can_be_set_explicitly(self):
        manifest = EncryptionManifest(kdf_salt=b"s", wrapped_data_key=b"k", version=2)
        assert manifest.version == 2

    def test_frozen_raises_on_field_assignment(self):
        manifest = EncryptionManifest(kdf_salt=b"s", wrapped_data_key=b"k")
        with pytest.raises(dataclasses.FrozenInstanceError):
            manifest.kdf_salt = b"other"  # type: ignore[misc]


class TestEncryptionState:
    def test_public_member_exists(self):
        assert EncryptionState.PUBLIC is not None

    def test_encrypted_member_exists(self):
        assert EncryptionState.ENCRYPTED is not None

    def test_accessible_by_value_public(self):
        assert EncryptionState("public") is EncryptionState.PUBLIC

    def test_accessible_by_value_encrypted(self):
        assert EncryptionState("encrypted") is EncryptionState.ENCRYPTED

    def test_public_and_encrypted_are_distinct(self):
        assert EncryptionState.PUBLIC is not EncryptionState.ENCRYPTED
