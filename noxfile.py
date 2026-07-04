# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Task automation for the generic-ml-cache monorepo (CA10).

``noxfile.py`` is the single source of truth for the project's gates — lint,
format, import contracts, type-check, tests, coverage. CI (`.github/workflows/`)
is a *thin caller* of these sessions, so there is exactly one definition of
"what green means". That kills the local/CI drift that caused the pyright-venv
bug: the gate that runs locally is byte-for-byte the gate that runs in CI.

Gate sessions build their own hermetic environments via the ``uv`` backend,
synced from the committed ``uv.lock`` (V3) so every gate runs the exact same
pinned resolution locally and in CI. The persistent root ``.venv`` is built only
by ``nox -s dev`` and is the IDE's interpreter — the gate sessions never touch it.

Usage::

    nox                 # the default gates: lint, imports, typecheck, tests
    nox -s green        # the full AGENTS.md 7-gate checklist in one env
    nox -s tests        # tests for every package (each in its own env)
    nox -s tests -- -k name   # extra args after -- pass through to pytest
    nox -s sonar        # write the per-package coverage XMLs Sonar ingests
    nox -s wheels       # assert built wheels ship py.typed + migrations (V15)
    nox -s dev          # (re)build the IDE .venv at ./.venv
"""

from __future__ import annotations

import os
import shutil
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

# Distribution name -> import package name, for ``--cov=``.
_IMPORT_NAME: dict[str, str] = {pkg: f"generic_ml_cache_{pkg}" for pkg in PACKAGES}

# The interpreters the test suite is gated on. Mirrors the CI matrix in
# ``.github/workflows/ci.yml`` so ``nox --python <ver> -s tests`` selects a
# matching session — each matrix job runs the suite under exactly one of these.
PYTHON_VERSIONS: tuple[str, ...] = ("3.10", "3.11", "3.12", "3.13")

# The security-critical secret scrubber runs on every command's log path, so a
# coverage gap there risks leaking tokens. It carries a per-module floor above the
# package-wide 80% average, which would otherwise hide a regression in this one file (CG8).
_SCRUBBER_MODULE = "generic_ml_cache_adapters.adapter.outbound.diagnostics.structlog_diagnostics_adapter"
_SCRUBBER_FLOOR = 90


def _install_all(session: nox.Session) -> None:
    """Sync the session env from the committed ``uv.lock`` (V3).

    ``--locked`` refuses a stale lockfile, so every gate — local or CI — runs
    against the exact pinned resolution; a dependency can only move via a
    deliberate ``uv lock --upgrade``, which is what makes the
    ``filterwarnings = ["error"]`` policy deterministic. All five packages
    install editable with every extra (dev toolchain, adapters' encryption).
    """
    session.run_install(
        "uv",
        "sync",
        "--locked",
        "--all-packages",
        "--all-extras",
        "--python",
        _session_python(session),
        external=True,
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )


def _session_python(session: nox.Session) -> str:
    """Path to this session's interpreter (to override the IDE-only .venv pin)."""
    return os.path.join(session.virtualenv.bin, "python")


@nox.session
def lint(session: nox.Session) -> None:
    """Gates 1-2 — ruff lint and format check (ruff at the locked version)."""
    _install_all(session)
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
    session.run("pyright", "--pythonpath", _session_python(session))


@nox.session(python=PYTHON_VERSIONS)
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
    session.run("ruff", "check", "packages/")
    session.run("ruff", "format", "--check", "packages/")
    session.run("lint-imports")
    session.run("pyright", "--pythonpath", _session_python(session))
    for pkg in PACKAGES:
        with session.chdir(f"packages/{pkg}"):
            session.run("python", "-m", "pytest")
    _run_scrubber_floor(session)


# The package whose wheel must also carry the SQL migrations. hatchling includes
# them only by DEFAULT (no explicit force-include in pyproject), so a src-tree
# move — e.g. the persistence pass relocating migrations under a sqlite/ folder —
# could silently drop them from the wheel; the `wheels` session guards that.
_MIGRATIONS_PACKAGE = "adapters"


@nox.session(venv_backend="none")
def wheels(session: nox.Session) -> None:
    """V15 — assert the BUILT wheels ship what a source-tree test cannot see:
    the PEP 561 ``py.typed`` marker in all five, and the SQL migrations in the
    adapters wheel. release.yml ``twine check``s wheel METADATA but never its
    CONTENTS, so a packaging regression (a dropped marker, an unpackaged
    migration) ships silently today. This builds each wheel with uv and inspects
    its archive members."""
    import tempfile
    import zipfile

    output_dir = Path(tempfile.mkdtemp(prefix="gmlc-wheels-"))
    try:
        for package in PACKAGES:
            session.run(
                "uv",
                "build",
                "--wheel",
                f"packages/{package}",
                "-o",
                str(output_dir),
                external=True,
            )

        problems: list[str] = []
        for package in PACKAGES:
            import_name = _IMPORT_NAME[package]
            built = list(output_dir.glob(f"{import_name}-*.whl"))
            if not built:
                problems.append(f"{package}: no wheel was built")
                continue
            members = zipfile.ZipFile(built[0]).namelist()

            if f"{import_name}/py.typed" not in members:
                problems.append(f"{package}: wheel is missing {import_name}/py.typed")

            if package == _MIGRATIONS_PACKAGE:
                source_dir = Path(f"packages/{package}/src/{import_name}/migrations")
                expected = sorted(
                    sql_file.name for sql_file in source_dir.glob("*.sql")
                )
                packaged = {
                    member.rsplit("/", 1)[1]
                    for member in members
                    if member.startswith(f"{import_name}/migrations/")
                    and member.endswith(".sql")
                }
                missing = [name for name in expected if name not in packaged]
                if missing:
                    problems.append(f"{package}: wheel is missing migrations {missing}")

        if problems:
            session.error("wheel-content check FAILED:\n  " + "\n  ".join(problems))
        session.log(
            f"wheel-content OK: py.typed present in all {len(PACKAGES)} wheels; "
            f"{_MIGRATIONS_PACKAGE} migrations packaged"
        )
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


@nox.session(venv_backend="none")
def dev(session: nox.Session) -> None:
    """(Re)build the persistent root ``.venv`` — the IDE interpreter.

    This is the one env the gate sessions never use. It holds every package
    editable plus the dev toolchain and pre-commit, so opening the project in
    an editor and running ``git commit`` both work with no further setup.
    """
    session.run(
        "uv",
        "sync",
        "--locked",
        "--all-packages",
        "--all-extras",
        external=True,
        env={"UV_PROJECT_ENVIRONMENT": ".venv"},
    )
