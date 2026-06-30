# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Entry point for the gmlcache CLI."""

from __future__ import annotations

try:
    import argcomplete
except ImportError:  # completion is a convenience; never let its absence break the CLI
    argcomplete = None

from generic_ml_cache_cli.infrastructure.parser import build_parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    if argcomplete is not None:
        # A no-op unless the shell is requesting completions (it sets _ARGCOMPLETE);
        # in that case it emits candidates and exits, so it never affects normal runs.
        argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    return args.func(args)
