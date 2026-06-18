# Contributing

Thanks for your interest in `generic-ml-cache`. This is an open project under the
Apache-2.0 license and contributions are welcome — bug reports, documentation,
tests, and code alike. It is early (alpha), so the most valuable
contributions right now are the ones that harden the core and the adapters.

By participating you agree to abide by the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

- **Report a bug.** Open an issue with the bug-report template. A failing test or
  an exact `gmlcache` command that reproduces the problem is gold.
- **Propose a feature.** Open an issue with the feature-request template. Check
  [`docs/ROADMAP.md`](docs/ROADMAP.md) first — your idea may already be planned,
  or deliberately out of scope (the cache is "dumb" on purpose).
- **Improve the docs.** If something was unclear, a doc fix helps the next person.
- **Send code.** See below.

## Development setup

You need Python 3.9 or newer. The only runtime dependency is `argcomplete` (Apache-2.0).

```bash
git clone https://github.com/danielslobozian/generic-ml-cache.git
cd generic-ml-cache
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running the tests

```bash
python -m pytest
```

The suite uses a deterministic fake client and does **not** require a real
`claude` / `codex` / `cursor-agent` to be installed, so it runs the same on Linux,
macOS, and Windows. Continuous integration runs it on all three across Python
3.9–3.13; please make sure it passes locally before opening a pull request.

For coverage:

```bash
python -m pytest --cov=generic_ml_cache
```

## Coding guidelines

- **Keep the cache dumb.** It adds no intelligence to the data. Determinism is the
  caller's responsibility. Proposals that make cache hits fuzzy or unpredictable
  will be declined — that is a design stance, not an oversight.
- **Protect the container-independence invariant.** Any change near checksums must
  preserve the rule that identical text checksums identically regardless of
  whether it lived in a file or a JSON string, and must keep newlines and tabs
  significant. Add tests.
- **Never store the prime directive or the command wording in a cassette.** A
  cassette records what the client did, not how it was instructed or launched.
- **Pure standard library at runtime.** Keep the package dependency-free; dev-only
  tools belong in the `dev` extra.
- **Cross-platform.** Store paths POSIX-style; do not assume a particular OS.
- **Match the existing style.** Code is formatted and linted with `ruff`.

```bash
pip install ruff
ruff check .
ruff format .
```

## Pull request process

1. Fork and branch from `main`.
2. Make your change with tests that cover it.
3. Ensure `python -m pytest` passes and `ruff check .` is clean.
4. Update [`CHANGELOG.md`](CHANGELOG.md) under `[Unreleased]`.
5. Open the pull request using the template and describe the *why*, not just the
   *what*. Link any related issue.

Maintainers review with a bias toward keeping the core small. See
[`GOVERNANCE.md`](GOVERNANCE.md) for how decisions get made.

## Reporting security issues

Please do **not** open a public issue for a vulnerability. Follow
[`SECURITY.md`](SECURITY.md) instead.
