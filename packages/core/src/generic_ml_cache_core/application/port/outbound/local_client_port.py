# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""LocalClientPort — the aggregate of a local CLI client's four role ports (W24).

A local client adapter represents ONE external system (e.g. the Claude CLI) and
answers every local role: managed runs, passthrough relays, availability probes, and
model listing. The four capabilities are split into role ports (V32/B-1 ISP) so each
consuming use case depends only on the slice it needs — a managed run does not depend
on model listing or version methods it never calls. This aggregate exists for the
ONE adapter that implements all of them (via ``ComposedLocalClient``) and for the
composition root that binds that single instance and hands each use case the narrow
role port it asked for.
"""

from __future__ import annotations

from generic_ml_cache_core.application.port.outbound.local_client_probe_port import (
    LocalClientProbePort,
)
from generic_ml_cache_core.application.port.outbound.local_model_listing_port import (
    LocalModelListingPort,
)
from generic_ml_cache_core.application.port.outbound.managed_local_runner_port import (
    ManagedLocalRunnerPort,
)
from generic_ml_cache_core.application.port.outbound.passthrough_local_runner_port import (
    PassthroughLocalRunnerPort,
)


class LocalClientPort(
    ManagedLocalRunnerPort,
    PassthroughLocalRunnerPort,
    LocalClientProbePort,
    LocalModelListingPort,
):
    """One local CLI client, implementing all four role ports (one adapter = one
    external system). ``resolve_executable`` is shared by the two runner ports and
    the probe — a legitimate role overlap, satisfied once by the adapter."""
