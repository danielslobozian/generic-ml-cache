# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionKind."""

from __future__ import annotations

import enum


class ExecutionKind(enum.Enum):
    """The type of an MlExecution — how gmlcache handles it.

    LOCAL_MANAGED     -- gmlcache launches the client in an isolated temporary
                         folder, manages grants, captures generated files, and
                         computes fingerprints. Full execution model.
    LOCAL_PASSTHROUGH -- gmlcache is a thin wrapper: raw native arguments are
                         passed verbatim to the client in the caller's folder.
                         No isolation, no grant management, no file capture.
                         stdout/stderr/exit can still be cached.
    API               -- gmlcache calls an ML provider API directly. No local
                         client executable, no filesystem isolation.
    API_PASSTHROUGH   -- gmlcache relays a raw provider-API request verbatim: the
                         opaque request bytes are forwarded to the upstream
                         endpoint and the raw response bytes are cached and
                         returned. Keyed on the body fingerprint, not a
                         structured request. Backs the caching HTTP gateway.
    """

    LOCAL_MANAGED = "local_managed"
    LOCAL_PASSTHROUGH = "local_passthrough"
    API = "api"
    API_PASSTHROUGH = "api_passthrough"
