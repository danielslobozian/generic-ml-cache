# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Smoke tests: the bootstrap package imports and exposes a version."""

import generic_ml_cache_bootstrap


def test_package_imports_and_has_version():
    assert isinstance(generic_ml_cache_bootstrap.__version__, str)
    assert generic_ml_cache_bootstrap.__version__
