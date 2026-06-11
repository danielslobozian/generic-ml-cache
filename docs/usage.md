# Usage

The complete reference for the `gmlcache` command line and the Python library.
For the concepts behind these commands, read [`design.md`](design.md); for the
formal contract, read [`SPEC.md`](SPEC.md).

> **Alpha.** The CLI and library surfaces may change before
> `1.0.0`. See [`ROADMAP.md`](ROADMAP.md).

## Install

```bash
pip install generic-ml-cache
```

Or from source:

```bash
pip install git+https://github.com/danielslobozian/generic-ml-cache.git
```

There are no runtime dependencies; the package is pure standard library. Python
3.9 or newer is required.

## The mental model in one paragraph

You run a real agentic CLI call *through* the cache. The first time, the cache
launches the real client in a private folder, captures its stdout / stderr /
exit code and any files it created, and stores all of that in a cassette keyed by
`(client, model, effort)` plus a checksum of your input. Every later run with the
same parameters and the same input replays the cassette instead of calling the
real client — instantly, deterministically, and offline if you ask.

## `gmlcache run`

Record-or-replay a call.

### Required arguments

| Flag | Meaning |
|------|---------|
| `--client {claude,codex,cursor}` | which CLI adapter to use |
| `--model MODEL` | the model identifier passed to the client |

`--model` and a prompt are required — without them there is nothing to identify
or execute.

### Effort (optional)

| Flag | Default | Meaning |
|------|---------|---------|
| `--effort EFFORT` | *(empty)* | reasoning-effort setting; omit to use the client's own default |

`(client, model, effort)` are the explicit launch parameters: part of the match
key and stored verbatim in the cassette. An empty effort is a distinct, valid key
value — a call with no effort is a different cassette from `--effort high`.

How each client uses it:

- **Claude** / **Codex** — effort is a separate axis. Pass `--effort high`, or
  omit it to let the client apply the model's own default.
- **Cursor** — effort is *encoded in the model id*. Use a full id from
  `gmlcache models cursor` (e.g. `gpt-5.3-codex-high`) and **omit** `--effort`;
  passing both appends the effort twice (`...-high-high`).

The cache never canonicalizes — it stores exactly what you give it — so pick one
convention per client and keep to it: `(cursor, "gpt-5.3-codex-high", "")` and
`(cursor, "gpt-5.3-codex", "high")` launch the same command but are two separate
cassettes.

### Supplying the input

The input is `{ context, prompt }`. Each half can be given inline or from a file:

| Flag | Meaning |
|------|---------|
| `--prompt PROMPT` | the prompt text, inline |
| `--prompt-file PROMPT_FILE` | read the prompt from a file |
| `--context CONTEXT` | the context text, inline |
| `--context-file CONTEXT_FILE` | read the context from a file |

Because the checksum is container-independent, `--prompt "hello"` and
`--prompt-file p.txt` (where `p.txt` contains exactly `hello`) produce the **same**
cache entry. Newlines and tabs are significant.

### System prompt

| Flag | Meaning |
|------|---------|
| `--system-prompt TEXT` | extra system prompt, inline |
| `--system-prompt-file FILE` | read the system prompt from a file |

The cache's prime directive is always injected ahead of whatever you supply here,
and neither the directive nor your system prompt is stored in the cassette.

### Input files

| Flag | Meaning |
|------|---------|
| `--input-file PATH` | a specific file the client will read in place (repeatable) |

Use this to tell the cache about specific files your client will read that live
**outside** its run folder. For each one the cache does exactly two things: it
**fingerprints the file's content** into the cache key (so a content change is a
different call), and it **opens the door** — the prime directive is widened to let
the client read those exact paths, which it is otherwise forbidden. The cache does
not deliver the files; your client reads them itself, in place, so your prompt
should reference them.

The key watches **content, not the name**: the fingerprint is a hash of the file's
bytes, so any file type works (text or binary), a rename with identical content is
still a hit, the order you pass them in is irrelevant, and two files with identical
content collapse to one. Only the fingerprint is stored in the cassette, never the
content. A missing file is an error.

```bash
gmlcache run --client claude --model sonnet \
  --prompt "Using db/schema.sql, write the migration." \
  --input-file db/schema.sql --input-file db/seed.sql
```

### Allow-path (scan folders)

| Flag | Meaning |
|------|---------|
| `--allow-path PATH` | a folder the client may scan/read; makes the call non-cacheable (repeatable) |

Use this when your client needs to **explore** a folder whose relevant contents
you can't enumerate in advance — e.g. "scan this source tree and find where X is
implemented." Because the cache cannot know what was read or whether it changed,
**any call that declares an allow-path runs fresh and stores nothing** (it is
*passthrough* — never a hit, never a recording). In offline mode such a call is an
error, since it can neither be served from cache nor run.

The client is granted read access to the folder two ways: the prime directive is
widened to permit it (all clients), and on **Claude** a real `--add-dir <folder>`
is added to the command. Codex and Cursor have their own per-client mechanisms,
but they are heterogeneous and unverified, so for now they rely on the directive
alone (hardening is tracked for a later release). Writes still stay confined to,
and captured from, the isolated run folder.

If you instead need the cache to *notice when specific files change*, declare them
with `--input-file` (fingerprinted, cacheable) rather than `--allow-path`
(unbounded, passthrough). The two are the bounded and unbounded ends of declared
read access.

```bash
gmlcache run --client claude --model sonnet \
  --prompt "Find every place we validate JWTs and summarise the approach." \
  --allow-path ./src --allow-path ./libs
```

### Modes

| Flag | Mode | Behavior |
|------|------|----------|
| *(default)* | `cache` | hit → replay; miss → call real, record, replay |
| `--offline` | `offline` | replay only; a miss is an error (exit 3) |
| `--force` | `refresh` | always call real and overwrite the cassette |
| `--mode {offline,cache,refresh}` | explicit | same as the shortcuts above |

### Other options

| Flag | Default | Meaning |
|------|---------|---------|
| `--store STORE` | `.gmlcache` | the cassette directory |
| `--executable EXECUTABLE` | `[executables]` config, else adapter `PATH` lookup | override the client binary (the "seam") |
| `--output-dir OUTPUT_DIR` | current directory | where replayed files are written |
| `--timeout TIMEOUT` | none | seconds before a real call is killed |
| `-v`, `--verbose` | off | print `gmlc:` diagnostics to stderr |

`--verbose` deliberately breaks byte-exact stderr fidelity; use it for debugging,
not for piping.

### Exit codes

| Code | Meaning |
|------|---------|
| *(replayed)* | in a hit, `gmlcache` exits with the **recorded** exit code |
| `3` | offline mode, cache miss |
| `4` | other cache error (unknown client, missing executable, bad cassette) |
| `2` | usage error (argparse) |

### Examples

Record on first run, replay forever after:

```bash
# First call: launches the real client, records a cassette.
gmlcache run --client claude --model sonnet --effort medium \
  --prompt "Summarize the attached notes." --context-file notes.txt

# Same call later: served from cache, no real client launched.
gmlcache run --client claude --model sonnet --effort medium \
  --prompt "Summarize the attached notes." --context-file notes.txt
```

Guarantee no real call happens (CI, reproducible builds):

```bash
gmlcache run --offline --client codex --model o4-mini --effort high \
  --prompt-file task.txt
# exits 3 if there is no matching cassette
```

Force a fresh recording:

```bash
gmlcache run --force --client cursor --model auto --effort low \
  --prompt "regenerate"
```

Write replayed files somewhere specific:

```bash
gmlcache run --client claude --model sonnet --effort medium \
  --prompt-file task.txt --output-dir ./build
```

## `gmlcache inspect`

Pretty-print a cassette so you can see exactly what was recorded.

```bash
gmlcache inspect .gmlcache/<match_key>.json
```

It shows the client / model / effort, the input checksum, the captured stdout /
stderr / exit code, and the list of captured files — everything the cache will
replay.

## `gmlcache doctor`

Report which configured clients are present on this machine and their versions.

```bash
gmlcache doctor
```

For each registered client it shows whether the executable was found (and where)
and the first line of its `--version` output. This is **advisory only**: it never
chooses a client, never restricts which model may run, and never gates a call —
it just tells you what is here. A client it cannot find is reported as missing,
not treated as an error.

Add `--json` for machine-readable output. In JSON mode every path emits valid
JSON — including absent clients — so a caller can parse the result without
special-casing.

## `gmlcache models`

List the models a client reports it can use.

```bash
gmlcache models            # every registered client
gmlcache models cursor     # one client
gmlcache models cursor --json
```

The list is **relayed from the client itself** — the cache runs the client's own
listing command and structures the output; it never hardcodes, guesses, or
substitutes a catalog. Because the client is already authenticated, the result
reflects what *that account* can actually reach.

There are three honest outcomes, and `--json` is always valid for each:

- the client is **absent** (`present: false`);
- the client is present but has **no listing command** (`supported: false` with a
  `reason`) — the cache simply says it does not know how to enumerate this
  client's models, rather than inventing a list;
- the client **listed** its models (`supported: true`, `models` populated), each
  entry an `id` (what you pass to `--model`), a human `name`, and `default` /
  `current` flags lifted from any marker the client printed.

Like `doctor`, this is advisory: it never selects, restricts, or gates a run.
Deciding *which* model to use stays with the caller. Of the built-in adapters,
only Cursor exposes a scriptable listing today; Claude and Codex report
"not supported" until a client ships one (the seam is ready when they do).

## Configuration

`run` reads its defaults — the resolution `mode`, the cassette `store`, and the
`timeout` — from one optional INI file, if it exists. The file is **opt-in**: it
is never written for you, on install or otherwise.

For each setting the winner is, in order: a **CLI flag**, then an **environment
variable**, then the **config file**, then the **built-in default**. So a flag
always wins, and the default (`mode = cache`, `store = .gmlcache`, no timeout)
applies when nothing else is set.

Location (override everything with `GMLCACHE_CONFIG=/path/to/file`):

- Windows — `%APPDATA%\generic-ml-cache\config.ini`
- otherwise — `$XDG_CONFIG_HOME/generic-ml-cache/config.ini` (or
  `~/.config/generic-ml-cache/config.ini`)

Format:

```ini
[defaults]
mode = cache
store = .gmlcache
timeout = 120
```

Environment variables: `GMLCACHE_MODE`, `GMLCACHE_STORE`, `GMLCACHE_TIMEOUT`
(and `GMLCACHE_CONFIG` to point at the file itself).

### Client executables

An optional `[executables]` section gives each client a persistent default for
the `--executable` seam — handy when a client is not on your `PATH`, or when you
keep several builds and want to pin one:

```ini
[executables]
claude = /opt/claude/bin/claude
codex  = /usr/local/bin/codex
```

It maps a client name to a path (or bare command); `run`, `doctor`, and `models`
all use it. It only changes *where* a client is launched from — never *which*
client or model runs. Precedence per client is `--executable` flag > this section
> the adapter's own `PATH` lookup; there is no environment layer (a single
variable cannot name a client). Unknown client keys are kept rather than
rejected — the adapter set is extensible — and a path is not checked at load: a
wrong one surfaces a clear error only when that client is actually launched.

## `gmlcache status`

Show the resolved configuration so behavior is never a mystery.

```bash
gmlcache status
gmlcache status --json
```

It prints which file would be read and whether it was found, then the effective
`mode` / `store` / `timeout` with the source of each value (`flag` / `env` /
`config` / `default`), and any configured client executables. It applies
environment and file settings but no `run` flags, since it describes the resting
configuration, not a particular call.

## `gmlcache --version`

Prints the installed version.

## Library use

The same machinery is importable. The public API is intentionally small during
the alpha and may grow before `1.0.0`.

```python
from generic_ml_cache import __version__
from generic_ml_cache.store import CassetteStore
from generic_ml_cache.cassette import Cassette

# Open a store and inspect what is in it.
store = CassetteStore(".gmlcache")
print(f"{len(store)} cassette(s) in the store")

for cassette in store:
    print(cassette.client, cassette.model, cassette.effort)
    print("  input checksum:", cassette.input_checksum)
    print("  exit:", cassette.response.exit)
    print("  files:", [f.path for f in cassette.response.files])
```

Loading a single cassette from disk:

```python
import json
from generic_ml_cache.cassette import Cassette

with open(".gmlcache/<match_key>.json", encoding="utf-8") as fh:
    cassette = Cassette.from_json(json.load(fh))
```

Computing a checksum the same way the cache does:

```python
from generic_ml_cache.checksum import checksum_input_data

key = checksum_input_data({"context": "some context", "prompt": "do the thing"})
```

For end-to-end recording and replay from Python, drive the three-mode resolver in
`generic_ml_cache.cache`; see [`design.md`](design.md) for how the pieces fit
together. A documented, stable library API is one of the items on the road to
`1.0.0`.

## Where things live

- Cassettes: in the `--store` directory (default `.gmlcache/`), one JSON file per
  recorded call, named by its match key.
- Replayed files: in `--output-dir` (default your current directory).
- Add `.gmlcache/` to your `.gitignore` unless you intend to commit recordings.
