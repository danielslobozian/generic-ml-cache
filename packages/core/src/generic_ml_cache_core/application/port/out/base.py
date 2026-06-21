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
from typing import ClassVar, List, Optional, Sequence

from generic_ml_cache_core.application.domain.model.model_info import ModelInfo as ModelInfo
from generic_ml_cache_core.application.domain.model.parsed_output import ParsedOutput
from generic_ml_cache_core.common.errors import ClientNotFound


class ClientAdapter(ABC):
    """Translate the neutral request into a concrete subprocess invocation."""

    #: short client name used in stored records and on the CLI (e.g. "claude")
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
        client_args: List[str],
        grants: Sequence[str] = (),
    ) -> List[str]:
        """Return the full argv to launch the client in ``run_dir``.

        ``client_args`` are passthrough arguments the caller wants appended to the
        launch verbatim -- the cache never interprets them. The adapter places
        them as late as its CLI allows while they are still read as flags: at the
        very end for clients whose prompt arrives on stdin, but **before the
        trailing prompt positional** for a client that takes the prompt in argv
        (otherwise they would be swallowed as prompt text rather than applied).

        ``grants`` are declared capabilities to *open* for this run (e.g. ``"net"``
        for network access). The adapter opens the matching door via
        :meth:`grant_setup` (a config-file mechanism) when granted. Grants enable;
        they never restrict (see ``docs/reference/grants.md``).
        """

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

    #: capabilities the cache can OPEN via the uniform config-file mechanism.
    GRANTS: ClassVar[tuple] = ("net", "read", "write", "shell", "web-search")

    def grant_setup(self, run_dir: Path, config_home: Path, grants: Sequence[str]) -> dict:
        """Render this client's own config file into ``config_home`` so the file --
        not a flag -- enables the granted capabilities, and return the environment
        the run needs (the client's config-home variable pointed at ``config_home``,
        e.g. ``{"CODEX_HOME": ...}``), seeding any credentials the relocated home
        needs along the way.

        This is the uniform door (v0.0.16): every client is driven the same way --
        a private config home, its home variable pointed at it, the settings file
        written inside. Writing into the run folder is always on (the client cannot
        produce output otherwise); the named grants open capability *beyond* that.
        Grants ENABLE, never restrict (``docs/reference/grants.md``); where a client has no
        file-level way to *close* a capability, that is a documented limit, not a
        door this method tries to shut.

        ``config_home`` is separate from ``run_dir``, so nothing written here is
        ever mistaken for client output or captured into a stored record. Default: no
        config home, empty env (adapters override).
        """
        return {}

    def grant_argv(self, grants: Sequence[str]) -> List[str]:
        """Operational flags a client FORCES for a grant its config file cannot
        express -- not a capability door, a transport necessity (Cursor's external
        network egress is ignored in its sandbox file headless, so ``net`` still
        needs ``--force``). Default: none.
        """
        return []

    def stream_event(self, raw_line: str) -> Optional[dict]:
        """Map ONE raw stdout line of this client's streaming output into a small
        normalized progress event, e.g. ``{"kind": "thinking"}`` or
        ``{"kind": "tool", "name": "web_search"}`` -- or ``None`` to ignore the
        line. Used only to feed the opt-in live stream (``--stream``; see
        ``stream.py``); it never affects what is recorded. Default: ignore every
        line (a client whose stream we do not normalize still shows the cache's own
        ``run.start`` / ``run.end`` events).
        """
        return None


def final_result_object(stdout: str):
    """Return the client's final result object, whether its output arrived as a
    single JSON object (``--output-format json``) or as the last ``type:result``
    line of an NDJSON stream (``--output-format stream-json``).

    Claude and Cursor emit *the same* result object in both forms, so the recorded
    answer and usage are identical either way -- this is what lets the live stream
    switch the client to streaming mode without changing the stored record. Returns
    ``None`` if nothing parseable is present (the adapter then degrades to raw
    stdout with no usage).
    """
    import json

    text = stdout.strip()
    if not text:
        return None
    # Single object (today's --output-format json): parses whole, in one shot.
    try:
        doc = json.loads(text)
        if isinstance(doc, dict):
            return doc
    except (json.JSONDecodeError, ValueError):
        pass  # not a single object -> it is an NDJSON stream; scan for the result
    last = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            last = event
    return last


def ensure_trailing_newline(text: str) -> str:
    """Append a newline to a client's answer when it lacks one.

    A client's structured (JSON) ``result`` carries the bare answer text, without
    the trailing newline a real CLI prints when it shows that answer. Without this
    the replayed answer butts against the next shell prompt, and a piped capture
    (``gmlcache run ... > file``) lacks the conventional final newline. Normalizing
    here -- at the adapter boundary -- keeps record and replay byte-identical (the
    recorded form simply includes the newline). Empty text is left untouched."""
    if text and not text.endswith("\n"):
        return text + "\n"
    return text
