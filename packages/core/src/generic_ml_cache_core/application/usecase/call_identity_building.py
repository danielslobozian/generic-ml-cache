# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared construction of a CallIdentity from a command's keyed inputs.

A probe and a run must derive byte-for-byte the same key, so the fingerprinting
and assembly live here, once, and both services call it. This is the *orchestration*
half — it performs the file I/O through the ``FileFingerprintPort`` — and then hands
the checksums to the domain factory (``ManagedCallIdentity.from_keyed_inputs``), which
owns the pure assembly rule. The port I/O cannot move into the domain (Rule 3), so the
split keeps the rule in the model and the I/O in the use-case layer.
"""

from __future__ import annotations

from generic_ml_cache_core.application.domain.model.identity.managed_call_identity import (
    KeyedCallInputs,
    ManagedCallIdentity,
)
from generic_ml_cache_core.application.port.outbound.file_fingerprint_port import (
    FileFingerprintPort,
)


def build_call_identity(
    file_fingerprint: FileFingerprintPort, keyed_inputs: KeyedCallInputs
) -> ManagedCallIdentity:
    """Fingerprint the keyed input files at the edge (only checksums enter the engine,
    never file content) and delegate the assembly to the domain factory, so a probe
    and a run derive byte-for-byte the same identity from one code path."""
    input_file_fingerprints = {
        input_file_path: file_fingerprint.fingerprint(input_file_path)
        for input_file_path in keyed_inputs.input_file_paths
    }
    return ManagedCallIdentity.from_keyed_inputs(keyed_inputs, input_file_fingerprints)
