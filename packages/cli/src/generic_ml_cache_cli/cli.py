# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
# PYTHON_ARGCOMPLETE_OK
"""The console-script entry module: re-exports ``main`` from the hexagonal entry point."""

from generic_ml_cache_cli.infrastructure.entry import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
