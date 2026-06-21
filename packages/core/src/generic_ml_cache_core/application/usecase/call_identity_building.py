# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared construction of a CallIdentity from a command's keyed inputs.

A probe and a run must derive byte-for-byte the same key, so the fingerprinting
and assembly live here, once, and both services call it. The Protocol is the
function's parameter type and stays beside it (one cohesive unit).
"""

from __future__ import annotations

from typing import List, Protocol

from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.port.out.file_fingerprint_port import FileFingerprintPort
from generic_ml_cache_core.common.checksum import fingerprint_arguments, text_checksum


class KeyedCallInputs(Protocol):
    """The raw, key-determining fields any command must expose to be keyed.

    Allow-paths and scan-trust are *not* here — they decide cacheability, not the
    key (see ``domain/service/cacheability.py``).
    """

    client: str
    model: str
    effort: str
    context: str
    prompt: str
    input_file_paths: List[str]
    client_args: List[str]
    grants: List[str]


def build_call_identity(
    file_fingerprint: FileFingerprintPort, keyed_inputs: KeyedCallInputs
) -> ManagedCallIdentity:
    """Fingerprint the keyed inputs (files at the edge, text in place) and assemble
    the managed identity. The file content never enters the engine — only
    checksums."""
    input_file_fingerprints = {
        input_file_path: file_fingerprint.fingerprint(input_file_path)
        for input_file_path in keyed_inputs.input_file_paths
    }
    client_args_fingerprint = (
        fingerprint_arguments(keyed_inputs.client_args) if keyed_inputs.client_args else None
    )
    return ManagedCallIdentity(
        client=keyed_inputs.client,
        model=keyed_inputs.model,
        effort=keyed_inputs.effort,
        context_fingerprint=text_checksum(keyed_inputs.context),
        prompt_fingerprint=text_checksum(keyed_inputs.prompt),
        input_file_fingerprints=input_file_fingerprints,
        client_args_fingerprint=client_args_fingerprint,
        grants=frozenset(keyed_inputs.grants),
    )
