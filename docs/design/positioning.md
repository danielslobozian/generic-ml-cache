<div align="center">

# Positioning — what gmlcache is, and what it is not

<sub>Design intent</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](../ROADMAP.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> **Status: positioning intent.** The licence *principle* below is load-bearing and stable; the
> detailed, provider-by-provider terms are not reproduced here because they change and must be
> checked against each provider's own current ToS/docs before being relied on. Cite primary
> sources, never a summary.

## The one sentence

**gmlcache is a single-user tool for discovering, testing, and integrating AI — it records a
real call once and replays it forever by checksum, across whichever subscriptions and APIs that
one user already holds.** It runs locally, on your machine, as you. It is **not** a gateway,
**not** a multi-user router, and **not** a way to make one subscription serve several people.

Everything below makes that sentence concrete.

## Where it shines

Every good fit is **one person**, using **seats/keys they already hold**, who wants to
understand, bound, and not re-pay for their own AI usage — while staying free to switch
providers and compare:

- **Discovery.** Run the same prompt across Claude, Codex, Cursor, or a raw API and compare
  outputs, behaviour, and token usage — paying for each unique call **at most once**, because
  exploration means re-running the same input constantly.
- **Cost-capped automation.** Drive a client in detached mode from your own scripts; each
  distinct call is metered and cached, so an hourly job or a build step **reuses tokens instead
  of re-burning them**.
- **Embedding AI in your own single-user app.** Import the engine, point it at whatever
  subscription/API you hold, and get recording + caching for free — free to swap providers
  underneath.
- **Personal CI / scripts**, where determinism and non-repeat-cost matter.
- **A client orchestrating cached detached siblings** — keep one interactive session as a thin
  conductor and push heavy work outward as cached one-shot calls.

## What it is NOT

- **Not a gateway.** A gateway centralises *many users'* traffic behind one endpoint and one
  set of credentials — multi-user by construction. gmlcache is mono-user by construction. If you
  want a gateway, the market already has them (LiteLLM, Portkey, Bifrost, Helicone, Kong,
  Cloudflare AI Gateway); we do not reinvent or compete with them.
- **Not a way to share or pool a subscription.** One personal seat is for one person.
- **Not a centralised team cache.** Used as intended it is local and personal: no multi-tenant
  namespace, no per-user scoping, no shared cache server handing results to other people.
- **Not authentication, authorization, or a security sandbox.** Execution folders isolate runs
  from each other for cleanliness and reproducibility, not as a security boundary.
- **Not a billing or pricing authority.** It records usage in **tokens** where the client
  exposes them; it never scrapes prices or asserts dollar costs.
- **Not a model router that chooses for you.** You switch model/tier and re-run to compare; it
  never silently picks a provider or optimises cost across them.

## It *could* be misused — and we say so

Being honest about this matters, so it is stated plainly rather than buried.

gmlcache drives the vendors' **own** CLIs, and to run them detached it relocates each client's
config home to a temporary folder and seeds it with the local user's credentials. That same
mechanism means a determined operator **could** feed it someone else's credentials and front one
subscription for many people. **The tool does not technically prevent this** — the same way
`git` does not prevent a bad commit.

We are not hiding behind "it's impossible," because it is not. We are saying it is **not the
intent**, and here is *why local is the clean line*:

- What keeps the permitted path permitted is **co-location** — the call runs on your machine, as
  you, indistinguishable from you running the official CLI yourself. Centralising it turns that
  fingerprint (one seat driven from a server, beside others) into exactly the shared/automated
  pattern providers detect and enforce against — **even if each call uses the rightful owner's
  token.**
- Pooling one seat behind several people is a violation of **your** provider's terms that **you**
  commit — identical in kind to handing out your password. gmlcache neither blesses nor enables
  it as a feature; respecting your provider's licence is your responsibility.

## The one licence line

Across the supported providers the load-bearing distinction is the same: **invoking the official
client (`claude -p`, `codex exec`, `cursor-agent -p`) as a subprocess, co-located as a single
user, is the blessed automation path; making your account available to others is the forbidden
one.** The providers are not symmetric in the detail, and the economics of the
subscription-backed path can change — so gmlcache describes the *capability* (wrap the official
CLI) and **never promises a cost outcome**, consistent with "tokens, not dollars; no scraper,
ever." Verify the specifics against each provider's current terms before relying on them.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](../ROADMAP.md)</sub>

</div>
