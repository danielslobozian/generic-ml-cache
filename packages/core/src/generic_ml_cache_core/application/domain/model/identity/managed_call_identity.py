# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ManagedCallIdentity."""

from __future__ import annotations

from dataclasses import dataclass, field

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.common.checksum import checksum_input_data


@dataclass(frozen=True)
class ManagedCallIdentity(CallIdentity):
    """The identity of a fully managed local call.

    Holds only processed fields — by the time it is constructed, every text input
    has been fingerprinted and every file path resolved to its content
    fingerprint. It is not the user's raw request.

    allow_paths (the folders the client may scan) enter the key as a *set*: a
    different set of allowed folders is a different call, so it must yield a new key.
    Their *contents* are not fingerprinted (unbounded, possibly modified between
    runs) — content stability is the caller's assertion via ``scan_trust``, which
    gates cacheability, not the key (see ``domain/service/cacheability.py``).
    """

    client: str
    model: str
    effort: str
    context_fingerprint: str
    prompt_fingerprint: str
    input_file_fingerprints: dict[str, str] = field(default_factory=dict)
    client_args_fingerprint: str | None = None
    system_fingerprint: str | None = None
    grants: frozenset[str] = field(default_factory=frozenset)
    allow_paths: frozenset[str] = field(default_factory=frozenset)

    def generate_key(self) -> str:
        key_data: dict[str, str] = {
            "kind": ExecutionKind.LOCAL_MANAGED.value,
            "client": self.client,
            "model": self.model,
            "effort": self.effort,
            "context": self.context_fingerprint,
            "prompt": self.prompt_fingerprint,
        }
        # The system prompt changes model behaviour, so it is part of the identity
        # (matching the API path). Absent system prompt -> omitted, so a call that
        # never set one keys identically to before this field existed.
        if self.system_fingerprint:
            key_data["system"] = self.system_fingerprint
        # Path-sensitive: the path enters the key alongside the content fingerprint.
        # A rename is a real change (the prompt may reference the file by name), so it
        # must yield a new key — soundness over hit-rate (prefer a miss to a wrong hit).
        for file_path, file_fingerprint in sorted(self.input_file_fingerprints.items()):
            key_data[f"file:{file_path}"] = file_fingerprint
        if self.client_args_fingerprint is not None:
            key_data[f"args:{self.client_args_fingerprint}"] = self.client_args_fingerprint
        if self.grants:
            key_data["grants"] = ",".join(sorted(self.grants))
        # The set of allowed folders is keyed (order-independent): adding or removing
        # a folder is a deliberate, different call. Omitted when empty, so calls with
        # no allow_paths key identically to before this field existed.
        if self.allow_paths:
            key_data["allow_paths"] = ",".join(sorted(self.allow_paths))
        return checksum_input_data(key_data)
