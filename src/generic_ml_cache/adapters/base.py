# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Client adapters: how to launch one agentic CLI and read its output.

An adapter is the *only* place that knows a specific CLI's flags. Everything
else in the cache works in terms of the neutral quartet
``(model, effort, prompt, context)`` plus a system prompt.

The v0.0.1 adapters below encode each CLI's own launch conventions (Claude
``--effort``; Codex ``model_reasoning_effort``; Cursor bakes effort into the
model id). Flags can drift, so every adapter:

* accepts an explicit ``executable`` override (the *executable seam*), and
* keeps launch wiring small and obvious so it is cheap to correct.

Adapters never decide caching policy and never read the caller's ambient files.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, List, Optional

from ..errors import ClientNotFound


class ClientAdapter(ABC):
    """Translate the neutral request into a concrete subprocess invocation."""

    #: short client name used in cassettes and on the CLI (e.g. "claude")
    name: ClassVar[str]
    #: default executable looked up on PATH when no override is given
    default_executable: ClassVar[str]

    def resolve_executable(self, override: Optional[str]) -> str:
        """Return an absolute path to the executable, honoring the seam."""
        candidate = override or self.default_executable
        # An explicit path (contains a separator) is used verbatim if it exists.
        if any(sep in candidate for sep in ("/", "\\")):
            p = Path(candidate)
            if p.exists():
                return str(p)
            raise ClientNotFound(f"executable not found at {candidate!r}")
        found = shutil.which(candidate)
        if not found:
            raise ClientNotFound(
                f"could not find {candidate!r} on PATH; pass --executable to override"
            )
        return found

    def prepare(self, run_dir: Path, context: str, prompt: str, system_prompt: str) -> None:
        """Write any input files the client needs into its isolated folder.

        Called *before* the pre-run snapshot, so anything written here is part of
        the baseline and is therefore not mistaken for client output. Default:
        no-op (the client receives everything via argv/stdin).
        """

    @abstractmethod
    def build_argv(
        self,
        executable: str,
        run_dir: Path,
        model: str,
        effort: str,
        context: str,
        prompt: str,
        system_prompt: str,
    ) -> List[str]:
        """Return the full argv to launch the client in ``run_dir``."""

    def stdin_payload(self, context: str, prompt: str, system_prompt: str) -> Optional[str]:
        """Optional text to feed on stdin. Default: nothing."""
        return None
