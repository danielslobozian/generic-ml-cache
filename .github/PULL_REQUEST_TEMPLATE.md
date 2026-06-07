<!--
Thanks for contributing! Please describe the *why*, not just the *what*.
See CONTRIBUTING.md for the full process.
-->

## Summary

<!-- What does this change and, more importantly, why? -->

## Related issue

<!-- e.g. "Closes #123". If there's no issue, briefly say why this is needed. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor / internal (no behavior change)
- [ ] Other (describe above)

## Checklist

- [ ] Tests cover this change, and `python -m pytest` passes locally.
- [ ] `ruff check .` and `ruff format --check .` are clean.
- [ ] I updated `CHANGELOG.md` under `[Unreleased]` (if user-facing).
- [ ] I updated the docs if behavior or the CLI/library surface changed.
- [ ] This change keeps the cache **dumb** and preserves the container-independent
      checksum invariant (or, if it intentionally touches that area, I explain why
      and added tests).
