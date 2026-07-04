# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ManagedCallIdentity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from generic_ml_cache_core.application.domain.model.execution.execution_kind import ExecutionKind
from generic_ml_cache_core.application.domain.model.identity.call_identity import CallIdentity
from generic_ml_cache_core.common.checksum import (
    checksum_input_data,
    fingerprint_arguments,
    text_checksum,
)


class KeyedCallInputs(Protocol):
    """The raw, key-determining fields any command must expose to be keyed.

    The *set* of allow-paths is keyed (a different set of folders is a different
    call). ``scan_trust`` is *not* here — it decides cacheability, not the key, and
    the folders' contents are never fingerprinted (see ``domain/service/cacheability.py``).

    All attributes are declared as read-only (@property) so frozen dataclasses
    satisfy this protocol without pyright emitting mutable-attribute mismatches.
    """

    @property
    def client(self) -> str: ...
    @property
    def model(self) -> str: ...
    @property
    def effort(self) -> str: ...
    @property
    def context(self) -> str: ...
    @property
    def prompt(self) -> str: ...
    @property
    def user_system_prompt(self) -> str | None: ...
    @property
    def input_file_paths(self) -> Sequence[str]: ...
    @property
    def allow_paths(self) -> Sequence[str]: ...
    @property
    def client_args(self) -> Sequence[str]: ...
    @property
    def grants(self) -> Sequence[str]: ...


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
    input_file_fingerprints: Mapping[str, str] = MappingProxyType({})
    client_args_fingerprint: str | None = None
    system_fingerprint: str | None = None
    grants: frozenset[str] = frozenset()
    allow_paths: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "input_file_fingerprints", MappingProxyType(dict(self.input_file_fingerprints))
        )
        object.__setattr__(self, "grants", frozenset(self.grants))
        object.__setattr__(self, "allow_paths", frozenset(self.allow_paths))

    @classmethod
    def from_keyed_inputs(
        cls, keyed_inputs: KeyedCallInputs, input_file_fingerprints: Mapping[str, str]
    ) -> ManagedCallIdentity:
        """Assemble the identity from a command's keyed inputs and the already-computed
        file fingerprints. Text inputs are checksummed here (pure); the file
        fingerprints are supplied by the caller, which owns the I/O — a domain factory
        reads no files (the same rule as ``Artifact.from_content``). A probe and a run
        both call this, so they derive byte-for-byte the same identity."""
        client_args_fingerprint = (
            fingerprint_arguments(keyed_inputs.client_args) if keyed_inputs.client_args else None
        )
        system_fingerprint = (
            text_checksum(keyed_inputs.user_system_prompt)
            if keyed_inputs.user_system_prompt
            else None
        )
        return cls(
            client=keyed_inputs.client,
            model=keyed_inputs.model,
            effort=keyed_inputs.effort,
            context_fingerprint=text_checksum(keyed_inputs.context),
            prompt_fingerprint=text_checksum(keyed_inputs.prompt),
            input_file_fingerprints=input_file_fingerprints,
            client_args_fingerprint=client_args_fingerprint,
            system_fingerprint=system_fingerprint,
            allow_paths=frozenset(keyed_inputs.allow_paths),
            grants=frozenset(keyed_inputs.grants),
        )

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
