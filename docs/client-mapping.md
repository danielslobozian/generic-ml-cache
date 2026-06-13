# Client mapping

How each piece of `gmlcache run` functionality is expressed when the cache
launches a client in detached mode. The aim is a plain, side-by-side reference:
*the functionality* → *how you ask for it in the cache* → *what the cache hands
each client*.

Three clients are supported, by executable name: **`claude`** (Claude Code),
**`codex`**, and **`cursor-agent`**.

> **Source of truth and accuracy.** These mappings are produced by each adapter's
> `build_argv` (`src/generic_ml_cache/adapters/`), which is authoritative — if this
> table and the code ever disagree, the code wins. The **write/trust-door** flags
> (the "Write access to the run folder" row) are *verified against the live CLIs*;
> the remaining flag choices are still *best-effort* and not yet verified, which is
> the work of release `0.0.8` (adapter hardening). Treat the unverified rows as
> "what the cache currently emits," not "what each CLI is confirmed to accept."

## Run inputs

| Functionality | In the cache | `claude` | `codex` | `cursor-agent` |
|---|---|---|---|---|
| Task instruction | `--prompt` / `--prompt-file` (required) | merged with context → `-p "<ctx>\n\n<prompt>"` | merged with context → positional argument | merged with context → `--print "<ctx>\n\n<prompt>"` |
| Supporting context | `--context` / `--context-file` | merged into the prompt above | merged into the prompt above | merged into the prompt above |
| Model | `--model` | `--model <model>` | `--model <model>` | `--model <model>` (effort baked into the id) |
| Reasoning effort | `--effort` (optional) | `--effort <effort>` (omitted if empty) | `-c model_reasoning_effort=<effort>` (omitted if empty) | appended to the model id: `<model>-<effort>` (omitted if empty) |
| System prompt | `--system-prompt` / `--system-prompt-file` (optional) | `--append-system-prompt <text>` | `-c experimental_instructions=<text>` | `--system-prompt <file>` (written into the run folder; cursor-agent's flag takes a path, not inline text) |
| Read access to a folder | `--allow-path` (optional; makes the call non-cacheable) | `--add-dir <folder>` + prime directive | prime directive only (hard mechanism deferred to 0.0.8) | prime directive only (hard mechanism deferred to 0.0.8) |
| Write access to the run folder | always (the cache's own isolated run dir) | `--permission-mode acceptEdits` | `--skip-git-repo-check --sandbox workspace-write -C <run-dir>` | `--trust` |
| Output capture | always | `--output-format text` | (default output) | `--print` |

Notes:

- **Context and prompt are concatenated** (`context\n\nprompt`) before being handed
  to any client. They are separate fields in the *cache key*, but a single string
  at the *client boundary*.
- The cache's **prime directive** (the isolation guardrail) is delivered through
  the same system-prompt channel as `--system-prompt`. So the guardrail is only as
  strong as each client honouring that flag — which is why it is a best-effort
  (soft) control.
- The **write/trust door** is opened by default for every run, because the client
  writes into the cache's own isolated, ephemeral run folder (its cwd). Headless
  clients otherwise refuse: Claude pauses on a write-permission prompt, Codex
  rejects an untrusted non-git directory and defaults to a read-only sandbox, and
  cursor-agent refuses an untrusted workspace. The grant is scoped to the run
  folder; read access to anything *outside* it is unchanged (prime directive plus
  the "Read access to a folder" row). Without it, a file-producing call recorded an
  empty `response.files` — the v0.0.5 record-path bug fixed in v0.0.6.

## Discovery (`doctor`, `models`)

| Functionality | In the cache | `claude` | `codex` | `cursor-agent` |
|---|---|---|---|---|
| Presence / version probe | `doctor` | `<exe> --version` | `<exe> --version` | `<exe> --version` |
| List available models | `models` | not supported (no scriptable list) | not supported (no scriptable list) | `cursor-agent --list-models` |

The cache never invents or hard-codes a model catalogue; it relays the client's
own list command or reports "not supported".

## Cache-only — never reaches the client

These shape what the *cache* does and are not passed to any client:

- `--mode` (`cache` / `offline` / `refresh`), `--force`, `--offline` — hit/miss policy.
- `--store`, `--timeout`, `--output-dir` — where cassettes live, the kill timeout, and where replayed files are written.
- `--input-file` — the client receives **no** flag for these. The cache fingerprints each file's content into the key and grants read access by widening the prime directive; the client simply reads the file in place because your prompt refers to it.
- The `[executables]` config — only chooses *which binary* to launch; invisible to the client.
- `inspect` and `status` invoke no client at all.
