# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ClientConfigPort — how one client expresses its run configuration.

Segregated from LocalClientPort on purpose: this is the *knowledge* of a client's
config layout (the grant file it reads, the credentials it needs, the env var that
points it at a redirected home). Core drives it — "I hold these grants, build the
config" — and materializes the descriptors itself. API adapters and passthrough do
not implement this; only local clients that run in an isolated config home do.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, Sequence, runtime_checkable

from generic_ml_cache_core.application.domain.model.run.client_config import (
    CredentialFile,
    GrantConfigFile,
)


@runtime_checkable
class ClientConfigPort(Protocol):
    """A client's config-and-credentials knowledge, as pure descriptors."""

    def build_grants_config_file(self, grants: Sequence[str]) -> Optional[GrantConfigFile]:
        """The config file that opens the granted capabilities, or ``None`` if the
        client needs no config file."""
        ...

    def get_token_files(self) -> List[CredentialFile]:
        """Credential/token sources to seed into the config home (may be empty)."""
        ...

    def config_home_env_var(self) -> Optional[str]:
        """Env var that must point the client at its config home (e.g.
        ``"CLAUDE_CONFIG_DIR"``), or ``None`` if the client uses no config home."""
        ...
