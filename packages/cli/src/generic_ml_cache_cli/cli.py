# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
# PYTHON_ARGCOMPLETE_OK
"""Backward-compatibility shim — imports moved to hexagonal sub-packages."""

from generic_ml_cache_cli.composition import (  # noqa: F401
    _db_conn_factory,
    _make_diag,
    _resolve_session,
    _resolve_token,
    _store_root,
)
from generic_ml_cache_cli.controllers.execution import _cmd_worker  # noqa: F401
from generic_ml_cache_cli.controllers.run import (  # noqa: F401
    GRANT_CHOICES,
    _relay_execution,
    _run_cached_execution,
)
from generic_ml_cache_cli.infrastructure.entry import main  # noqa: F401
from generic_ml_cache_cli.infrastructure.parser import build_parser  # noqa: F401
from generic_ml_cache_cli.presenters.shared import render_banner  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(main())
