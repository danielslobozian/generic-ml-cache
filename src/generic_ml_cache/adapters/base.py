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
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, List, Optional

from ..errors import ClientNotFound
from ..usage import ParsedOutput


@dataclass
class ModelInfo:
    """One model a client reports it can use. Purely what the client relayed.

    ``id`` is the string a caller would pass as ``--model``; ``name`` is the
    client's own human label. ``default``/``current`` mirror any marker the
    client printed. The cache neither invents nor validates these fields.
    """

    id: str
    name: str
    default: bool = False
    current: bool = False


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

    def version_argv(self, executable: str) -> List[str]:
        """Argv that prints the client's version. Default: ``<exe> --version``.

        Override only if a client uses a different flag. Advisory: used by the
        ``doctor`` command for discovery; it never affects caching.
        """
        return [executable, "--version"]

    def models_argv(self, executable: str) -> Optional[List[str]]:
        """Argv that makes the client list the models it can use, or ``None``.

        Return ``None`` when the client has no scriptable way to enumerate its
        models -- discovery then reports "not supported" for this client rather
        than inventing or substituting a list. When non-``None``, the output is
        relayed through :meth:`parse_model_list`. Because the client is the one
        already authenticated, a relayed list reflects what *that account* can
        actually reach. Advisory: never selects, restricts, or gates a run.
        """
        return None

    def parse_model_list(self, stdout: str) -> List[ModelInfo]:
        """Structure the client's raw model-list output into ``ModelInfo``.

        Only called when :meth:`models_argv` returns a command; override the two
        together. Keep parsing to plain structuring of what the client printed.
        """
        raise NotImplementedError

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

    def parse_output(self, stdout: str) -> ParsedOutput:
        """Lift the clean answer text and the usage envelope out of the client's
        raw stdout.

        The cache runs each client in its **structured (JSON) output mode** so it
        can read usage -- which means raw stdout is no longer the bare answer but a
        JSON object (or JSON-lines stream) with the answer as one field and the
        token counts beside it. The adapter is the only place that knows its own
        client's structure, so it does the extraction here: it returns the answer
        text (which the cache then hands the caller on stdout, exactly as a plain
        client would) and the normalized :class:`~..usage.Usage` it read.

        Default: the client was *not* run in a structured mode, so stdout already
        *is* the answer and there is no usage to read. Adapters that switch their
        client to JSON override this.

        An override MUST degrade rather than raise: if the output cannot be parsed
        (an unexpected shape, a truncated stream), return ``ParsedOutput(stdout,
        None)`` so a parsing surprise never breaks the core call -- the caller
        still gets the client's output, just without a usage envelope.
        """
        return ParsedOutput(text=stdout, usage=None)

    def read_access_argv(self, paths: List[str]) -> List[str]:
        """Extra argv granting the client read access to ``paths`` (directories).

        Default: none -- the client relies on the soft prime-directive door only.
        Adapters with a real per-client read mechanism override this (Claude:
        ``--add-dir``). Codex and Cursor have one too but it is heterogeneous and
        currently unverified, so they stay on the directive until adapter
        hardening verifies them against the live CLIs.
        """
        return []

    def write_access_argv(self, run_dir: Path) -> List[str]:
        """Extra argv opening the client's WRITE/TRUST door for its own ``run_dir``.

        Headless clients refuse to write by default: they pause on a permission
        prompt, or decline a workspace they have not been told to trust. Without
        this the client only *narrates* the file it was asked to produce, the
        before/after diff captures nothing, and a file-producing call records an
        empty ``response.files`` -- the v0.0.5 record-path bug this fixes.

        The run folder is the client's own isolated, ephemeral sandbox, so writing
        into it is the normal case and the grant is **on by default**. It is scoped
        to that folder: reads *outside* it are unaffected and remain gated by the
        prime directive and :meth:`read_access_argv`. Unlike ``read_access_argv``
        (appended after :meth:`build_argv`), each adapter splices this into
        ``build_argv`` itself, because some CLIs take the prompt as a trailing
        positional and reject flags placed after it.

        Default: none. The per-client flags below are verified against the live
        CLIs (see ``docs/client-mapping.md``); adapter hardening keeps them small
        and correctable should a CLI change.
        """
        return []
