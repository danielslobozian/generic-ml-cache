<div align="center">

# Client Mapping

<sub>Core documentation</sub>

<br>

[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)

</div>

---

Adapters translate gmlcache execution requests into backend-specific mechanics.
Two adapter kinds exist: **CLI adapters** drive a local binary subprocess;
**API adapters** call a provider's REST API directly.

The `--client` value selects the adapter. gmlcache resolves its kind automatically — no
separate `--provider` or `--kind` flag is needed.

## CLI adapters

| Client | Binary | Prompt delivery | File capture | Usage reported |
|---|---|---|---|---|
| `claude` | `claude` | stdin (large prompts) or argv | yes (output files) | input, output, cache read/write tokens; `cost_usd` |
| `codex` | `codex` | argv | no | input, output tokens (no cache counts) |
| `cursor` | `cursor-agent` | argv | no | unconfirmed — verify live |
| `vibe` | `vibe` | argv (no stdin) | unconfirmed — verify live | none — not in Vibe's `-p` output |

**All CLI adapters** respect `--executable` (or `[executables]` config) to pin a
non-`PATH` binary. `allow_paths` and `scan_trust` make a run uncacheable.

**Vibe** differs from the other CLI clients: the model is selected via the
`VIBE_ACTIVE_MODEL` env var (Vibe has no `--model` flag); `effort` maps to Vibe's
`thinking`, which is config-only, so v1 leaves it at the model default; Vibe exposes
no token usage in programmatic (`-p`) output; and Vibe has **no OS sandbox**, so
read/write grants are advisory — it can read paths outside the run folder. Auth is
read from the user's `~/.vibe` (`.env` / config).

Cursor has no inference API and is a CLI adapter only.

## API adapters

API adapters call the provider's REST endpoint directly using stdlib `urllib` —
no SDK dependency. The provider's API key is read from the environment (see below)
or passed via `api_key=` at construction time.

| Client | Endpoint | Auth env var | `cache_read` | `cache_write` | `reasoning` | `cost_usd` |
|---|---|---|---|---|---|---|
| `anthropic` | `POST /v1/messages` | `ANTHROPIC_API_KEY` | ✓ (`cache_read_input_tokens`) | ✓ (`cache_creation_input_tokens`) | — (folds into output) | — |
| `gemini` | `POST /v1beta/models/{model}:generateContent` | `GEMINI_API_KEY` | ✓ (`cachedContentTokenCount`) | — | ✓ (`thoughtsTokenCount`) | — |
| `openai` | `POST /v1/responses` | `OPENAI_API_KEY` | ✓ (`input_tokens_details.cached_tokens`, automatic) | — (read-only cache) | ✓ (`output_tokens_details.reasoning_tokens`) | — |
| `mistral` | `POST /v1/chat/completions` | `MISTRAL_API_KEY` | ✓ (`prompt_tokens_details.cached_tokens`) | — (read-only cache) | — | — |

`cost_usd` is always `None` for API adapters — none of the four providers return a
dollar figure per call. Usage a call did not report is `None` (unknown), never `0`.

### Context and system prompt mapping

| gmlcache field | Anthropic | Gemini | OpenAI |
|---|---|---|---|
| `context` | `system` (joined with `user_system_prompt` by `\n\n`) | `systemInstruction.parts[0]` | `instructions` (joined with `user_system_prompt` by `\n\n`) |
| `user_system_prompt` | `system` (joined with `context`) | `systemInstruction.parts[1]` | `instructions` (joined with `context`) |
| `prompt` | `messages[{role:user}]` | `contents[{role:user}]` | `input[{role:user}]` |

### Effort mapping

| gmlcache `effort` | Anthropic | Gemini | OpenAI |
|---|---|---|---|
| `""` / `"low"` | no thinking | `thinkingLevel: low` | no reasoning |
| `"medium"` | — (not mapped) | `thinkingLevel: medium` | — (not mapped) |
| `"high"` | — (not mapped) | `thinkingLevel: high` | — (not mapped) |

Anthropic and OpenAI effort mapping is not yet implemented; `effort` is accepted but
ignored. Gemini maps `effort` to `generationConfig.thinkingConfig.thinkingLevel`.

## Common request fields

| gmlcache field | Meaning |
|---|---|
| `client` | Adapter name; selects CLI or API adapter automatically |
| `model` | Model identifier passed verbatim to the adapter |
| `effort` | Reasoning/effort level where the adapter supports it |
| `context` | Background text (maps to system role) |
| `prompt` | User question or instruction |
| `user_system_prompt` | Optional extra system instruction supplied at call time |
| `input_file_paths` | Files fingerprinted for identity (CLI adapters only) |
| `allow_paths` | Paths the adapter may scan; makes the run uncacheable |
| `grants` | Declared capabilities (network, shell, read, write) — CLI adapters only |
| `client_args` | Opaque passthrough arguments included in cache identity |
| `tags` | Free-form labels attached to the stored execution (never in identity) |
| `session_id` | Associates the run with a session for reporting |

---

<div align="center">

<sub>[Documentation home](README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../README.md)</sub>

</div>
