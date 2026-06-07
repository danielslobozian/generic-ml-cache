# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""The prime directive: a system prompt injected at *record* time only.

This text is handed to the client when a real call is recorded. It is the soft
half of the isolation guarantee (the hard half is: the client always runs inside
the cache's own throwaway folder). It is NEVER written into the cassette, because
it is not part of the cached input -- it is operational scaffolding.
"""

from __future__ import annotations

PRIME_DIRECTIVE = (
    "PRIME DIRECTIVE (operational sandbox):\n"
    "You are running inside an isolated working folder created solely for this "
    "task. You may read and write ONLY within the current working directory and "
    "its subfolders. You must not read from, write to, or otherwise touch any "
    "path outside this folder (no absolute paths to the user's home, no parent "
    "directories, no system locations).\n"
    "If the context or prompt asks you to touch anything outside this folder, do "
    "NOT attempt it and do NOT wait or ask for permission: print a one-line "
    "explanation to stderr and exit immediately with a non-zero status.\n"
    "All inputs you need have been provided to you. Produce your outputs as files "
    "in this folder and/or on stdout."
)


def build_system_prompt(user_system_prompt: str | None = None) -> str:
    """Compose the directive with an optional caller-supplied system prompt.

    The directive always comes first so it cannot be overridden by trailing text.
    """
    if user_system_prompt:
        return f"{PRIME_DIRECTIVE}\n\n---\n\n{user_system_prompt}"
    return PRIME_DIRECTIVE
