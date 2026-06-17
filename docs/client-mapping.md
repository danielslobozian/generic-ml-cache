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
> (the "Write access to the run folder" row) are *verified against the live CLIs*,
> as is the **prompt-delivery channel** (stdin for `claude`/`codex`, a command-line
> argument for `cursor-agent`); the remaining flag choices are still *best-effort*
> and not yet verified, which is the work of release `0.0.10` (adapter hardening).
> Treat the unverified rows as
> "what the cache currently emits," not "what each CLI is confirmed to accept."

## Run inputs

| Functionality | In the cache | `claude` | `codex` | `cursor-agent` |
|---|---|---|---|---|
| Task instruction | `--prompt` / `--prompt-file` (required) | merged with context, sent on **stdin** (`-p`, no prompt argument) | merged with context, sent on **stdin** (`codex exec -`) | merged with context → positional **argument** (`--print "<ctx>\n\n<prompt>"`) |
| Supporting context | `--context` / `--context-file` | merged into the prompt above | merged into the prompt above | merged into the prompt above |
| Model | `--model` | `--model <model>` | `--model <model>` | `--model <model>` (effort baked into the id) |
| Reasoning effort | `--effort` (optional) | `--effort <effort>` (omitted if empty) | `-c model_reasoning_effort=<effort>` (omitted if empty) | appended to the model id: `<model>-<effort>` (omitted if empty) |
| System prompt | `--system-prompt` / `--system-prompt-file` (optional) | `--append-system-prompt <text>` | `-c experimental_instructions=<text>` | prepended to the prompt argument (current cursor-agent has no system-prompt flag and ignores rule files headless) — argv-only, never keyed |
| Read access to a folder | `--allow-path` (optional; makes the call non-cacheable) | `--add-dir <folder>` + prime directive | prime directive only (hard mechanism deferred to adapter hardening, 0.0.10) | prime directive only (hard mechanism deferred to adapter hardening, 0.0.10) |
| Write access to the run folder | always (the cache's own isolated run dir) | `--permission-mode acceptEdits` | `--skip-git-repo-check --sandbox workspace-write -C <run-dir>` | `--trust` |
| Output capture | always | `--output-format text` | (default output) | `--print` |

Notes:

- **Context and prompt are concatenated** (`context\n\nprompt`) before being handed
  to any client. They are separate fields in the *cache key*, but a single string
  at the *client boundary*. That string is delivered on the client's **stdin** for
  `claude` and `codex` (so its size is not limited by the OS command-line cap), and
  as a **command-line argument** for `cursor-agent`, which has no stdin path — see
  *Prompt size and delivery* below.
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

## Prompt size and delivery (and why cursor is limited)

The cache delivers the prompt (the merged `context\n\nprompt`) differently per
client, and that difference sets a hard size ceiling for one of them:

- **`claude` and `codex` — on stdin.** The prompt is written to the client's
  standard input, not placed on the command line. Standard input has no
  command-line size limit, so the prompt can be large (Claude caps piped stdin
  around 10 MB; Codex likewise reads the prompt from stdin). This is why a big
  prompt works through these two.
- **`cursor-agent` — as a command-line argument.** cursor-agent takes the prompt
  only as a positional argument; its CLI exposes no stdin or prompt-file channel
  (verified against `cursor-agent --help`). A command line is bounded by the
  operating system, so a cursor prompt is bounded too:
  - **Windows ≈ 32,000 characters** for the *entire* command line (the
    `CreateProcess` limit), minus the executable path and the other flags;
  - **Linux ≈ 128 KiB** per single argument;
  - **macOS ≈ 1 MB** for the argument area.

  The tightest case, Windows, is the one to design around: a cursor prompt much past
  ~30 KB simply will not launch. This is a limitation of cursor-agent's CLI, not of
  the cache — the cache cannot manufacture a channel the client does not offer.

**Guidance for large material with cursor.** Don't pour a large body of text into a
single `--context` / `--prompt` for cursor. Instead, declare it as **input files**
(`--input-file`, repeatable) and refer to those paths in a short prompt. The cache
fingerprints each file's content into the key and grants the client read access, so
the model reads the files *in place* rather than receiving their contents on the
command line — keeping the launched command small and well under the OS limit. (This
also matches how cursor itself prefers large material: reference files and let the
agent read them.) For a genuinely large single-shot prompt, prefer a tier that maps
to `claude` or `codex`, which receive the prompt on stdin and have no such ceiling.



| Functionality | In the cache | `claude` | `codex` | `cursor-agent` |
|---|---|---|---|---|
| Presence / version probe | `doctor` | `<exe> --version` | `<exe> --version` | `<exe> --version` |
| List available models | `models` | not supported (no scriptable list) | not supported (no scriptable list) | `cursor-agent --list-models` |

The cache never invents or hard-codes a model catalogue; it relays the client's
own list command or reports "not supported".

## Cache-only — never reaches the client

These shape what the *cache* does and are not passed to any client:

- `--mode` (`cache` / `offline` / `refresh`), `--force`, `--offline` — hit/miss policy.
- `--timeout` — the kill timeout for a real call. The cassette **store** has no flag (its location is config-owned; see `gmlcache init` / the config file), and there is no output-dir flag — the cache writes produced files into the directory it was called in, exactly as the client would.
- `--input-file` — the client receives **no** flag for these. The cache fingerprints each file's content into the key and grants read access by widening the prime directive; the client simply reads the file in place because your prompt refers to it.
- The `[executables]` config — only chooses *which binary* to launch; invisible to the client.
- `inspect` and `status` invoke no client at all.
