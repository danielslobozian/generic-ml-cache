"""Request."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Request:
    """A single cache request -- the full identity of one client call.

    Fields:
        client: registered client name (e.g. ``claude``, ``codex``, ``cursor``).
        model:  the model id, passed through to the client verbatim.
        effort: reasoning-effort level; an empty string means "unset" (the client
            applies its own default). A distinct value in the key.
        context: optional supporting material, merged ahead of the prompt when the
            client is invoked. Part of the key.
        prompt: the task instruction (required for a run). Part of the key.
        user_system_prompt: an optional caller-supplied system prompt, layered
            after the cache's prime directive at record time. NOT part of the key.
        input_files: declared files the client will read *in place*, as
            ``{absolute_path: content_sha256}``. Only the content fingerprint
            enters the key (folded into ``input_data``); the paths serve solely to
            open the read-door at record time and are never keyed. Same content ->
            same key (rename-invariant), identical contents collapse to one entry,
            and order is irrelevant.
        allow_paths: declared folders the client may *scan* (read) whose contents
            are unbounded and cannot be fingerprinted (absolute paths). Their mere
            presence makes the call **non-cacheable** -- it runs fresh and stores
            nothing (passthrough) -- unless scan-trust is explicitly enabled. Never
            keyed; they only open the read-door (directive + a client's hard read
            flag where available).
        client_args: extra raw arguments appended verbatim to the client launch --
            an escape hatch for client features the cache does not model. They DO
            enter the key: the same modeled inputs with different extra args are a
            different call and get their own cassette, because anything that
            changes the invocation can change the output. Only their *fingerprint*
            is keyed (folded into ``input_data``), so the raw args -- which may
            carry secrets -- never land in a cassette; the raw values are used
            solely to build the command line at record time. Order is significant
            (CLI flags are positional); an empty list keys identically to a call
            with no passthrough, so existing cassettes are untouched.
        grants: declared capabilities to *open* for this run (e.g. ``net`` for
            network access). Enablement only -- the cache opens the door and never
            tries to close it (see ``docs/reference/grants.md``). They enter the key (a
            granted call is a distinct call and gets its own cassette), kept
            readable and order-independent: a sorted, de-duplicated set folded into
            ``input_data``. ``net`` does not make the call non-cacheable -- choosing
            the cache is the intent to cache, and ``--force`` is the lever for a
            live re-fetch. Absent -> nothing keyed, so prior cassettes are untouched.

    The key is derived from ``client``, ``model``, ``effort`` and ``input_data``
    only -- i.e. context, prompt and the input-file fingerprints (see
    ``input_data``). The user system prompt, the prime directive and the
    allow-path folders are all record-time scaffolding and are deliberately
    excluded from the key.
    """

    client: str
    model: str
    effort: str
    context: str
    prompt: str
    user_system_prompt: Optional[str] = None
    input_files: Dict[str, str] = field(default_factory=dict)
    allow_paths: List[str] = field(default_factory=list)
    client_args: List[str] = field(default_factory=list)
    grants: List[str] = field(default_factory=list)

    @property
    def input_data(self) -> Dict[str, str]:
        data = {"context": self.context, "prompt": self.prompt}
        for sha in self.input_files.values():
            data[f"input_file:{sha}"] = sha
        # Passthrough args enter the key by *fingerprint* only -- the raw strings
        # (which may hold secrets) never reach input_data and so never a cassette.
        # Order is preserved (CLI flags are positional). Absent -> nothing added,
        # so the key is byte-for-byte what it was before passthrough existed.
        if self.client_args:
            digest = hashlib.sha256("\x00".join(self.client_args).encode("utf-8")).hexdigest()
            data[f"client_args:{digest}"] = digest
        # Grants enter the key too -- a granted call is a distinct call (a net run
        # and a no-net run of the same prompt produce different output). Unlike
        # client_args they are non-secret and few, so they are kept readable; and
        # they are order-independent, so the set is sorted and de-duplicated for a
        # stable key. Absent -> nothing added, so prior cassettes are untouched.
        if self.grants:
            data["grants"] = ",".join(sorted(set(self.grants)))
        return data

    @property
    def allowed_read_paths(self) -> List[str]:
        """All paths the read-door is opened for: input files + allow-path folders."""
        return sorted([*self.input_files, *self.allow_paths])

    @property
    def add_dir_paths(self) -> List[str]:
        """Allow-path folders, sorted -- granted via a client's hard read flag
        (e.g. Claude's ``--add-dir``) where one exists."""
        return sorted(self.allow_paths)

    @property
    def requires_passthrough(self) -> bool:
        """True when the call declares unfingerprintable folders -> not cacheable."""
        return bool(self.allow_paths)
