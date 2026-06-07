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
| `--effort EFFORT` | the reasoning-effort setting passed to the client |

`(client, model, effort)` are the explicit launch parameters. They are part of
the match key and are stored verbatim in the cassette.

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
| `--executable EXECUTABLE` | adapter default | override the client binary (the "seam") |
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
