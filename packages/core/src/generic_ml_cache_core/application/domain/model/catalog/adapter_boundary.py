# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""AdapterBoundary — the kind of external integration an adapter represents."""

from __future__ import annotations

import enum


class AdapterBoundary(enum.Enum):
    """How an adapter reaches its client.

    ``LOCAL_CLI`` — drives a locally-installed CLI in a subprocess (managed +
    passthrough). ``API`` — calls a remote provider over HTTP. The boundary is the
    adapter's *identity* axis; execution mode is a per-request concern carried in
    :attr:`AdapterDescriptor.supported_modes`.
    """

    LOCAL_CLI = "local-cli"
    API = "api"
