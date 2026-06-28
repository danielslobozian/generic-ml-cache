# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Enable ``python -m generic_ml_cache``."""

from __future__ import annotations

from generic_ml_cache_cli.infrastructure.entry import main

if __name__ == "__main__":
    raise SystemExit(main())
