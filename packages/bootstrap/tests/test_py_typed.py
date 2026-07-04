# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Packaging guard (IaC-1): the distribution ships its PEP 561 ``py.typed`` marker.

Without it, downstream type checkers silently treat this package as untyped — so
the marker disappearing is a real (and easy-to-miss) regression. Keep it runnable.
"""

from pathlib import Path

import generic_ml_cache_bootstrap


def test_py_typed_marker_is_shipped():
    package_dir = Path(generic_ml_cache_bootstrap.__file__).parent
    assert (package_dir / "py.typed").is_file(), "py.typed marker is missing from bootstrap"
