---
description: Cut a release PR — bump VERSION, generate CHANGELOG from commits, commit, push, open PR
allowed-tools: Bash, Read, Edit, Write
---

## Context — gather before doing anything

Run the following shell commands first to establish the baseline:

```bash
# 1. Current version and today's date
cat VERSION
date +%Y-%m-%d

# 2. Confirm we're on main and it's clean
git branch --show-current
git status --short

# 3. All commits since the last release tag (these become the CHANGELOG)
git log v$(cat VERSION | tr -d '[:space:]')..HEAD --oneline --no-merges

# 4. ROADMAP section for the upcoming version (for context on what was planned)
# (computed after you know the new version — see step 2 below)
```

Also read:
- `CHANGELOG.md` lines 1–60 — to match the existing entry style exactly
- `docs/ROADMAP.md` — to find and mark the new version's milestone as released

---

## Step 1 — verify the working tree is clean

If `git status --short` shows uncommitted changes, stop and tell the user.
If we are not on `main`, stop and tell the user.

---

## Step 2 — compute the new version

This project always bumps the **minor** segment (format is always `0.x.0`):

```bash
current=$(cat VERSION | tr -d '[:space:]')
minor=$(echo $current | cut -d. -f2)
new_minor=$((minor + 1))
new_version="0.${new_minor}.0"
echo "Bumping $current → $new_version"
```

---

## Step 3 — create the release branch

```bash
git pull
git checkout -b release/<new_version>
```

---

## Step 4 — generate the CHANGELOG entry (ML step)

Using the commit log from step 0 as raw material:

1. Group commits by type — `feat`/`fix`/`chore`/`docs`/`style`/`test` prefixes are hints,
   but read the message to understand the actual user-visible change.
2. Write a `## [<new_version>] - <today>` section with subsections as needed:
   - **Added** — new user-visible features or capabilities
   - **Changed** — behaviour or API changes (including renames, signature changes)
   - **Fixed** — bug fixes
   - **Removed** — deleted features, files, or dependencies
3. Each bullet must name the affected package(s) in parentheses — `(core)`, `(cli)`,
   `(daemon)`, or combinations — matching the style of existing entries.
4. Omit pure style, format, and CI-only commits unless they affect the developer
   experience (e.g. a new pre-commit hook that developers must install).
5. The tone and granularity must match the existing CHANGELOG entries — read them
   before writing.

---

## Step 5 — update the three files

### VERSION
Replace the single line with the new version string.

### CHANGELOG.md
Insert the new `## [<new_version>]` block immediately after `## [Unreleased]`, before
the previous release entry. Do not touch any other section.

### docs/ROADMAP.md
Find the heading `### <new_version> —` and append `*(released <today>)*` to that line.
If no such heading exists, skip this file entirely (do not create a stub).

---

## Step 6 — run the gates

```bash
.venv/bin/ruff check packages/
.venv/bin/ruff format --check packages/
```

If either fails, stop and report. Do not commit broken code.

---

## Step 7 — commit, push, open PR

```bash
git add VERSION CHANGELOG.md docs/ROADMAP.md
```

Commit message format:
```
chore(release): cut <new_version> (<one-line summary of the headline change>)
```

Then:
```bash
git push -u origin release/<new_version>
```

PR body must include:
- A bullet list of the headline changes (mirror the CHANGELOG Added/Changed/Removed sections)
- A test plan checklist (all gates pass, version numbers correct, CHANGELOG renders)

Use:
```bash
gh pr create --title "chore(release): cut <new_version> (<summary>)" --body "..." --base main
```

Return the PR URL to the user when done.
