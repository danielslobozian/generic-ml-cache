# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Descriptors a client adapter returns so core can prepare a managed run's config.

Core knows it *holds these grants and must build the config*; it does not know how
any specific client expresses that. The adapter answers with these descriptors —
the config file to write and the credential files to seed — and core materializes
them into the run's private config home. Pure data: no filesystem side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GrantConfigFile:
    """The config file a client reads to learn which capabilities are open.

    ``file_name`` is written verbatim into the run's config home; ``content`` is
    the exact bytes (e.g. Claude's ``settings.json``, Codex's ``config.toml``).
    """

    file_name: str
    content: bytes


@dataclass(frozen=True)
class CredentialFile:
    """A credential/token source to seed into the client's private config home.

    ``source`` may be a file or a directory; core copies it to ``target_name``
    inside the config home (a directory is copied recursively).
    """

    source: Path
    target_name: str
