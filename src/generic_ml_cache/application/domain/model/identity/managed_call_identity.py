# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ManagedCallIdentity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional

from generic_ml_cache.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache.common.checksum import checksum_input_data


@dataclass(frozen=True)
class ManagedCallIdentity(CallIdentity):
    """The identity of a fully managed local call.

    Holds only processed fields — by the time it is constructed, every text input
    has been fingerprinted and every file path resolved to its content
    fingerprint. It is not the user's raw request.

    allow_paths (permission grants to scan folders) are NOT a field here: they do
    not enter the key and travel separately to the client runner.
    """

    client: str
    model: str
    effort: str
    context_fingerprint: str
    prompt_fingerprint: str
    input_file_fingerprints: Dict[str, str] = field(default_factory=dict)
    client_args_fingerprint: Optional[str] = None
    grants: FrozenSet[str] = field(default_factory=frozenset)

    def generate_key(self) -> str:
        key_data: Dict[str, str] = {
            "kind": ExecutionKind.LOCAL_MANAGED.value,
            "client": self.client,
            "model": self.model,
            "effort": self.effort,
            "context": self.context_fingerprint,
            "prompt": self.prompt_fingerprint,
        }
        # Path-sensitive: the path enters the key alongside the content fingerprint.
        # A rename is a real change (the prompt may reference the file by name), so it
        # must yield a new key — soundness over hit-rate (prefer a miss to a wrong hit).
        for file_path, file_fingerprint in sorted(self.input_file_fingerprints.items()):
            key_data[f"file:{file_path}"] = file_fingerprint
        if self.client_args_fingerprint is not None:
            key_data[f"args:{self.client_args_fingerprint}"] = self.client_args_fingerprint
        if self.grants:
            key_data["grants"] = ",".join(sorted(self.grants))
        return checksum_input_data(key_data)
