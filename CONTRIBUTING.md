# Contributing

Thanks for your interest in `generic-ml-cache`. This repository is a monorepo of four
Apache-2.0 packages — the hexagonal kernel [`generic-ml-cache-core`](packages/core),
the infrastructure adapters [`generic-ml-cache-adapters`](packages/adapters), the
terminal client [`generic-ml-cache-cli`](packages/cli), and the local HTTP daemon
[`generic-ml-cache-daemon`](packages/daemon) — and contributions are welcome: bug
reports, documentation, tests, and code alike.

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md), and
all code is held to the standard in [`AGENTS.md`](AGENTS.md).

## Ways to help

- **Report a bug.** Open an issue with the bug-report template. A failing test or an
  exact `gmlcache` command that reproduces the problem is gold.
- **Propose a feature.** Open an issue with the feature-request template. Check
  [`docs/ROADMAP.md`](docs/ROADMAP.md) first — your idea may already be planned, or
  deliberately out of scope (the cache is "dumb" on purpose).
- **Improve the docs.** If something was unclear, a doc fix helps the next person.
- **Send code.** See below.

## Repository layout

```
packages/core/      generic-ml-cache-core     — hexagonal kernel: domain model, use
                                                cases, port contracts. Zero runtime deps.
packages/adapters/  generic-ml-cache-adapters — concrete port implementations: SQLite,
                                                filesystem, ML clients, API adapters,
                                                encryption, metrics. Depends on core.
packages/cli/       generic-ml-cache-cli      — the gmlcache terminal client. Depends
                                                on core + adapters.
packages/daemon/    generic-ml-cache-daemon   — local HTTP daemon and gateway proxy.
                                                Depends on core + adapters.
```

Dependency arrow: `adapters → core`; `cli → core + adapters`; `daemon → core + adapters`.
The core never imports adapters, cli, or daemon — not even in dev dependencies.
See [`AGENTS.md`](AGENTS.md) for the full structure and dependency rules.

## Development setup

You need Python 3.10 or newer. Install all five packages editable — core first, since
the others depend on it:

```bash
git clone https://github.com/danielslobozian/generic-ml-cache.git
cd generic-ml-cache
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e "packages/core[dev]"        # the kernel
pip install -e "packages/adapters[dev]"    # the infrastructure adapters
pip install -e "packages/bootstrap[dev]"   # the composition root
pip install -e "packages/cli[dev]"         # the terminal client (provides gmlcache)
pip install -e "packages/daemon[dev]"      # the local HTTP daemon
```

Editable installs mean a change in any package is picked up immediately by the others.

## Running the tests

Each package has its own suite; run them from the package directory:

```bash
( cd packages/core     && python -m pytest )
( cd packages/adapters && python -m pytest )
( cd packages/cli      && python -m pytest )
( cd packages/daemon   && python -m pytest )
```

The suites use a deterministic fake client and do **not** require a real `claude` /
`codex` / `cursor-agent`, so they run the same on Linux, macOS, and Windows. Continuous
integration runs each package on all three across Python 3.10–3.13; please make sure all
four pass locally before opening a pull request.

Coverage is enforced by each package's `pytest` configuration (thresholds in
`pyproject.toml`); running `pytest` is sufficient to check it.

## Coding guidelines

All code must meet [`AGENTS.md`](AGENTS.md) — read it before sending code. In short:

- **Keep the cache dumb.** It adds no intelligence to the data; determinism is the
  caller's responsibility. Proposals that make cache hits fuzzy or unpredictable will
  be declined — that is a design stance, not an oversight.
- **Protect the container-independence invariant.** Any change near checksums must
  preserve the rule that identical text checksums identically whether it lived in a
  file or an inline string, and must keep newlines and tabs significant. Add tests.
- **Never persist the prime directive or the command wording in an execution record.**
  A stored execution records what the client did, not how it was instructed or launched
  — only fingerprints, never raw prompts or context.
- **Nothing baked in but structure.** The library never hardcodes a location or reads a
  config file; the data source and configuration are injected (AGENTS §5).
- **Cross-platform.** Store paths POSIX-style; do not assume a particular OS.
- **Match the existing style.** Code is formatted and linted with `ruff`; green means
  **both** checks pass:

```bash
ruff check packages/
ruff format --check packages/
```

## Pull request process

1. Fork and branch from `main`.
2. Make your change with tests that cover it.
3. Ensure the affected package's `pytest` passes and both `ruff check packages/` and
   `ruff format --check packages/` are clean.
4. Update the root [`CHANGELOG.md`](CHANGELOG.md) under `[Unreleased]`. The two
   packages are versioned in lockstep, so the root changelog is the single source for
   both — note which package(s) a change touches.
5. Open the pull request using the template and describe the *why*, not just the *what*.
   Link any related issue.

Maintainers review with a bias toward keeping the core small. See
[`GOVERNANCE.md`](GOVERNANCE.md) for how decisions get made.

## Reporting security issues

Please do **not** open a public issue for a vulnerability. Follow [`SECURITY.md`](SECURITY.md)
instead.
