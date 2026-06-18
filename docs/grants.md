# Grants

How `gmlcache` opens a capability a launched step needs — and, just as important,
what it deliberately does **not** try to do.

## The one-sentence model

A *grant* is a door the cache opens for the client it launches, so the client can do
something a step requires that it otherwise cannot do headless. You ask for one with
`run --grant <capability>` (repeatable). The first grant is **`net`** — web /
network access.

## Enablement, not restriction (and not a security boundary)

The cache's job with grants is to make a client **able**, never to **limit** it. It
opens doors; it does not close them. This is a deliberate line, and the analysis
behind this feature is why it is drawn here.

Each client was probed against its live CLI to see whether its own configuration
could both **enable** a capability and **deny** it. Enabling worked everywhere.
Denying did not:

- Denying a high-level tool (say, file-write) while leaving the shell open simply
  routes the action through the shell — the agent writes the file with `echo >`
  instead. A denial is only real if it also closes the shell, and even then:
- one client returns the contents of a workspace file with **no tool call at all** —
  it pulls files into the model's context outside any permission gate, so no `Read`
  or shell denial stops it.

The lesson: a client cannot be reliably *confined* by the configuration the cache
controls. Promising a limit the client itself will not honour is worse than
promising none. So the cache does not pretend to be a sandbox or a security
boundary. It enables; it does not restrict.

A user who genuinely needs hard limits provides them at a layer that can enforce
them — a dedicated OS user with restricted read/write, or a container — exactly as
they would run any untrusted tool. The cache's responsibility is to do the enabling
well; containing a misbehaving client is the deployment's job, not the cache's.

## What is already open, and what `net` adds

Most file and exec capability is **already** open, via the write/trust door (since
0.0.6) and the read-widening of `--input-file` / `--allow-path`:

- **Write + exec inside the run folder** — on by default, because the client runs in
  the cache's own isolated folder and the door is scoped to it.
- **Read of declared files/folders** — `--input-file` (content fingerprinted into
  the key) and `--allow-path` (a scanned folder).

What is **not** open today is the **network**. Codex runs under a write-sandbox with
the network off, and the prime directive tells every client to stay in its folder.
`--grant net` is the door that lets a step reach the web when it needs a live source
— "retrieve the latest data, then analyse it."

The grant vocabulary, first slice:

| Grant | Meaning |
|---|---|
| `net` | The client may reach the network — fetch URLs, hit APIs, browse. |
| `web-search` | A sibling for clients that expose a distinct *search* tool (Codex's live web search), separate from raw fetch. |

Deferred, named so a future request has somewhere to land: **sub-agent** and **MCP**
grants. Neither was validated against the live CLIs, so neither ships until it is.

## Caching a granted call

A web-granted call is cached **like any other call — on the ordinary prompt key**.
The web is a *source the model consulted* while producing the recorded answer, not a
separate input the cache keys on. Choosing to run through the cache is itself the
intent to cache; a caller who wants a live call reaches for `refresh` (or calls the
client directly).

The honest consequence, recorded plainly: the live page is **not** fingerprinted
into the key, so a cassette holds *the answer as of when it was recorded*. This is
the same property the cache already lives with for model nondeterminism — a hit
replays the recorded result, and `refresh` is the lever for a fresh one. Deciding
when freshness matters is the caller's responsibility, never the cache's.

(This is a deliberate difference from `--allow-path`, which stays non-cacheable by
default. That earlier choice targets *locally mutated* folders a caller edits
between runs, where silent staleness is likeliest and least expected. A web source
named in the prompt is treated like the prompt's own content: cached, with `refresh`
as the escape.)

## Two control models (why the adapters differ)

The three clients gate capability in two fundamentally different ways, and a grant
has to speak both:

- **Codex — an OS sandbox.** Coarse but absolute. `sandbox_mode` and
  `network_access` decide what is possible at the process level, so what they permit
  they permit completely, and what they forbid cannot be reached by any route (tool
  *or* shell). The trade: no fine-grained, per-tool permission — it is all-or-nothing
  per axis.
- **Claude Code and cursor-agent — tool permissions.** Fine-grained per tool, but
  enforced at the tool layer, so anything reachable through an *un*-gated tool
  (notably the shell) is reachable regardless. Good for enabling a specific
  capability; weak as a boundary.

For *enablement* — the cache's only job here — both models suffice: each client can
be told to open the network. The difference only bites if one tries to restrict,
which the cache does not.

## Per-adapter mechanics — validated 2026-06-18 against the live CLIs

What opening `net` means for each adapter, and the limits found.

### `claude` (Claude Code)

- **Door:** allow Claude's web tools (`--allowedTools WebSearch WebFetch`).
- **Reaches the web:** yes — verified against the live CLI through the cache: with
  the grant Claude fetched an external URL via WebFetch and returned the real value;
  without it WebFetch is denied (a permission prompt it cannot satisfy headless).
  The prime directive does not block the WebFetch path.
- **Limit:** Claude has no process-level *network switch* — egress from a subprocess
  is not gated by its permission config. So "no web" means not opening the path, not
  a hard network block. The cache does not attempt the hard block (see *enablement,
  not restriction*).

### `codex`

- **Door:** open the network in the `workspace-write` sandbox the run already uses
  (`network_access = true`).
- **Reaches the web:** yes — with the toggle off the fetch is blocked at the
  sandbox; with it on it succeeds (verified the same way).
- **Strength:** this is the one *leak-proof* gate — the sandbox decides network at
  the process level, so the grant is honoured completely.
- **`web-search`:** Codex exposes a distinct live web search (`web_search`); the
  grant turns it on. With it off the search tool does not fire — though the model may
  still answer trivia from prior knowledge, which is the model's memory, not a live
  search.

### `cursor-agent`

- **Door:** `--force` ("Force allow commands unless explicitly denied"; `--yolo`
  is its alias). `--trust` (the write door) alone does NOT open the network.
- **Reaches the web:** yes — verified against the live cursor-agent: `--trust`
  alone is blocked at the sandbox; `--trust --force` reaches an external fetch.
- **Limit:** cursor-agent's `sandbox.json` `networkPolicy` is ignored under headless
  `-p` (an upstream bug), so the door is the `--force` flag, not a config file.

## How this was validated

Each capability was tested by running the client **headless, in an untrusted temp
folder** (the cache's own execution shape), with the capability turned on and off,
and judged by a **real effect**, never the model's self-report:

- **Web** used a throwaway local HTTP server returning a fresh **random nonce that
  never appeared in any prompt**. A pass required *both* the server logging the
  request *and* the nonce appearing in the client's output — so no answer from memory
  could pass, and the result is decided by the server's own log, not the agent's
  claim.
- **File and shell** effects were judged by an artifact on disk (a file created, a
  random secret read back) — never by a token the model could echo in prose.

These probes also surfaced the confinement limits above (the shell escape and the
out-of-band file read), which is precisely why the cache's stance is enablement
only. One operational detail worth recording: relocating Codex's config home
(`CODEX_HOME`) also relocates its credentials, so the cache seeds auth into the home
it controls; the other two keep their existing login in place.
