# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Task automation for the generic-ml-cache monorepo (CA10).

``noxfile.py`` is the single source of truth for the project's gates — lint,
format, import contracts, type-check, tests, coverage. CI (`.github/workflows/`)
is a *thin caller* of these sessions, so there is exactly one definition of
"what green means". That kills the local/CI drift that caused the pyright-venv
bug: the gate that runs locally is byte-for-byte the gate that runs in CI.

Gate sessions build their own hermetic environments via the ``uv`` backend
(fast, reproducible). The persistent root ``.venv`` is built only by
``nox -s dev`` and is the IDE's interpreter — the gate sessions never touch it.

Usage::

    nox                 # the default gates: lint, imports, typecheck, tests
    nox -s green        # the full AGENTS.md 7-gate checklist in one env
    nox -s tests        # tests for every package (each in its own env)
    nox -s tests -- -k name   # extra args after -- pass through to pytest
    nox -s sonar        # write the per-package coverage XMLs Sonar ingests
    nox -s dev          # (re)build the IDE .venv at ./.venv
"""

from __future__ import annotations

import os
from pathlib import Path

import nox

nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True
nox.options.sessions = ["lint", "imports", "typecheck", "tests"]

# Packages discovered from the layout, so adding a 5th (e.g. bootstrap) is picked
# up automatically — there is no package list to edit here or in CI.
PACKAGES: tuple[str, ...] = tuple(
    sorted(p.parent.name for p in Path("packages").glob("*/pyproject.toml"))
)

# Per-package install extras. Everything gets [dev]; adapters also needs its
# optional [encryption] extra (cryptography) for the full test suite.
_EXTRAS: dict[str, str] = {"adapters": "[dev,encryption]"}

# Distribution name -> import package name, for ``--cov=``.
_IMPORT_NAME: dict[str, str] = {pkg: f"generic_ml_cache_{pkg}" for pkg in PACKAGES}

# The security-critical secret scrubber runs on every command's log path, so a
# coverage gap there risks leaking tokens. It carries a per-module floor above the
# package-wide 80% average, which would otherwise hide a regression in this one file (CG8).
_SCRUBBER_MODULE = (
    "generic_ml_cache_adapters.adapter.out.diagnostics.structlog_diagnostics_adapter"
)
_SCRUBBER_FLOOR = 90


def _editable_specs() -> list[str]:
    """``-e packages/<pkg><extra>`` for every package.

    Installed together in one call so uv resolves the inter-package
    ``==0.2X.*`` pins against the local editables instead of fetching PyPI.
    """
    specs: list[str] = []
    for pkg in PACKAGES:
        specs += ["-e", f"packages/{pkg}{_EXTRAS.get(pkg, '[dev]')}"]
    return specs


def _install_all(session: nox.Session) -> None:
    session.install(*_editable_specs())


def _session_python(session: nox.Session) -> str:
    """Path to this session's interpreter (to override the IDE-only .venv pin)."""
    return os.path.join(session.virtualenv.bin, "python")


@nox.session
def lint(session: nox.Session) -> None:
    """Gates 1-2 — ruff lint and format check. No package install needed."""
    session.install("ruff>=0.15")
    session.run("ruff", "check", "packages/")
    session.run("ruff", "format", "--check", "packages/")


@nox.session
def imports(session: nox.Session) -> None:
    """Gate 6 — hexagonal import contracts (import-linter)."""
    _install_all(session)
    session.run("lint-imports")


@nox.session
def typecheck(session: nox.Session) -> None:
    """Gate 7 — pyright static type checking.

    Pointed at this session's interpreter via ``--pythonpath`` so it resolves
    imports from the hermetic env rather than the IDE-only root ``.venv``.
    """
    _install_all(session)
    session.install("pyright>=1.1")
    session.run("pyright", "--pythonpath", _session_python(session))


@nox.session
@nox.parametrize("package", PACKAGES)
def tests(session: nox.Session, package: str) -> None:
    """Gates 3-5 — per-package test suite (run from the package dir so its own
    pyproject pytest/coverage config applies, exactly as CI does)."""
    _install_all(session)
    with session.chdir(f"packages/{package}"):
        session.run("python", "-m", "pytest", *session.posargs)


def _run_scrubber_floor(session: nox.Session) -> None:
    """Enforce the per-module coverage floor for the secret scrubber. Runs the full
    adapters suite (every test that touches the module counts) with coverage scoped
    to that one file; ``-o addopts=`` drops the package-wide ``--cov`` so the floor
    applies to the module alone."""
    with session.chdir("packages/adapters"):
        session.run(
            "python",
            "-m",
            "pytest",
            "-o",
            "addopts=",
            f"--cov={_SCRUBBER_MODULE}",
            f"--cov-fail-under={_SCRUBBER_FLOOR}",
        )


@nox.session
def scrubber_floor(session: nox.Session) -> None:
    """CG8 — the secret scrubber's per-module coverage floor (see _SCRUBBER_FLOOR)."""
    _install_all(session)
    _run_scrubber_floor(session)


@nox.session
def sonar(session: nox.Session) -> None:
    """Write the per-package coverage XMLs that Sonar ingests.

    The scanner itself stays in CI (needs the token + the scan action); this
    session reproduces the exact numbers Sonar will report.
    """
    _install_all(session)
    for pkg in PACKAGES:
        session.run(
            "python",
            "-m",
            "pytest",
            f"packages/{pkg}/tests",
            f"--cov={_IMPORT_NAME[pkg]}",
            f"--cov-config=packages/{pkg}/pyproject.toml",
            f"--cov-report=xml:packages/{pkg}/coverage.xml",
        )


@nox.session
def green(session: nox.Session) -> None:
    """The AGENTS.md 7-gate "green" checklist, in a single environment."""
    _install_all(session)
    session.install("ruff>=0.15", "pyright>=1.1")
    session.run("ruff", "check", "packages/")
    session.run("ruff", "format", "--check", "packages/")
    session.run("lint-imports")
    session.run("pyright", "--pythonpath", _session_python(session))
    for pkg in PACKAGES:
        with session.chdir(f"packages/{pkg}"):
            session.run("python", "-m", "pytest")
    _run_scrubber_floor(session)


@nox.session(venv_backend="none")
def dev(session: nox.Session) -> None:
    """(Re)build the persistent root ``.venv`` — the IDE interpreter.

    This is the one env the gate sessions never use. It holds every package
    editable plus the dev toolchain and pre-commit, so opening the project in
    an editor and running ``git commit`` both work with no further setup.
    """
    session.run("uv", "venv", ".venv", external=True)
    session.run(
        "uv",
        "pip",
        "install",
        *_editable_specs(),
        "pre-commit",
        "nox",
        external=True,
        env={"VIRTUAL_ENV": ".venv"},
    )
