<div align="center">

# Data handling — persistence, tagging, and encryption

<sub>Design intent</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](../ROADMAP.md)

</div>

---

**Status: largely implemented.** Persistence depth (meter/cache/dataset), tagging and tag
query, dataset export, and at-rest encryption have landed. One documented gap remains:
encryption covers the content blobs, not the metadata index (see the crypto notes). This
records the model and the sharp edges; the [roadmap](../ROADMAP.md) sequences the work.

## The model: a persistence ladder plus orthogonal toggles

gmlcache's data behavior is **one ordered choice plus two independent toggles**. The core
stays stateless and simply honors whatever policy the inbound driver injects per call.

**Persistence depth** is a single ordered setting — each level a superset of the one below:

| Depth | Stores | Behavior |
|---|---|---|
| `meter` | metadata / usage only | every call runs; usage + tag analytics, no replay |
| `cache` *(default)* | + output | replay on hit |
| `dataset` | + input | replay **and** a labeled `(input, output)` corpus |

Modeling persistence as *depth* — not two independent booleans — makes the one degenerate
state, **input stored without output, unrepresentable**: the input's only value is as the
key to / `X` of an output, so you cannot reach `dataset` without passing through `cache`.

Two genuinely orthogonal toggles sit around the ladder:

| Toggle | Default | On |
|---|---|---|
| **At-rest encryption** (token-keyed; covers whatever is persisted) | off | encrypted, erasable |
| **Tagging + tag query** | off | label + query executions |

Tagging is useful at *every* depth — even `meter` (tagged cost/usage analytics with nothing
stored). Encryption is a no-op at `meter` and protects what is persisted at `cache` /
`dataset`. Usage/metadata recording is the always-on baseline.

**Non-identity rule.** Tags (and sessions) are *metadata*. They never enter the execution
identity (the fingerprint), or the same input under a different tag would miss. This is the
rule the roadmap already states for `session_id`.

## Composed modes (examples)

- **Cache** (today): output cached, input fingerprinted, no tags, no encryption.
- **Private cache**: + encryption. Lose the disk → nothing readable without the token;
  erase = drop the key (crypto-shred).
- **Dataset builder**: + input persistence + tags → a queryable, labeled `(input, output)`
  corpus, exportable for distillation/evaluation. Encryption optional — plaintext-local if
  you do not care, encrypted if you do. Changing your mind is cheap: re-running an
  already-cached call at dataset depth **back-fills the input onto the existing entry on the
  hit** (the input is in the request, so no re-run is needed) — exactly as relabeling
  accumulates tags. Enriching the stored data is the user's decision.
- **Usage meter**: output caching **off** + tags/usage on → a metering/observability
  front-end. It can still compute the fingerprint to report *would-be* hit/miss
  ("you'd have saved N runs") without storing anything.

## The privacy boundary

- **Inputs are never stored unless you opt in.** Outputs *are* stored whenever caching is
  on — and an output can contain personal data present in the input. So "only fingerprints
  are stored" describes the **input** side; the **output** side is covered by encryption,
  not by omission.
- **Client-held key / zero-knowledge at rest.** The app **never stores the encryption secret
  or the key it derives**; the secret is supplied at runtime (env var, file, or command) and
  the key exists only in memory during the call. This protects data **at rest** (disk theft,
  backups, a curious admin); it does **not** protect a compromised running process mid-call.
  **Lost secret = unrecoverable** — which is also the erasure property.
- **Disclosure, not enforcement.** Persisting without encryption = plaintext on local disk.
  For a local, privacy-indifferent user that is a valid choice; the docs must state the
  trade-off so it is informed, but the system does not forbid it.

## Crypto cautions (for when encryption is built)

Encryption uses a **vetted library** (`cryptography`: AES-256-GCM + HKDF-SHA256), behind an
optional `[encryption]` extra — permissively licensed, `pip`-only, no OS-level software, so the
base install carries no crypto dependency. The scheme still merits an independent cryptographic
review. How the implementation meets — or defers — each caution:

1. **Derive the key; never use the secret raw.** *Done.* Token → HKDF-SHA256 → a
   key-encryption-key that wraps a random **data key**; content is encrypted under the data
   key. Nothing stored relates to the token except the wrapped key, which doubles as the
   verifier (a wrong token fails its AEAD tag).
2. **Secret entropy is security-critical.** *Done.* gmlcache generates the token (256-bit,
   url-safe); no outside passphrase is accepted, so a password-hardening KDF (Argon2id) is
   unnecessary.
3. **Key the lookup index, not just the blobs.** **The known gap.** Encryption covers the
   content blobs; the SQLite metadata stays plaintext, so the content *fingerprints* (and
   model names, tags, timestamps) are visible to someone holding the encrypted store. The
   content itself is protected; *which* (possibly low-entropy) inputs were seen is not. Keying
   the index (`HMAC(key, fingerprint)`) is future hardening.
4. **AEAD bound to context.** *Done.* AES-256-GCM with domain-separated associated data, so a
   tampered or *swapped* blob fails to decrypt.
5. **Store-wide, not per-entry.** *Done.* On or off for the whole local store — no
   public/private split (that was the scope idea). Off: blobs stay content-addressed and
   deduplicated. On: everything persisted is encrypted under the one key. Enabling/disabling is
   a crash-safe migration (stage → atomic commit marker → per-file swap; recovery self-heals a
   half-done migration on the next open).

## Dataset caveat

Cached outputs include the model's **mistakes**; the cache cannot tell a good output from a
bad one and must not try (that is interpreting output — out of scope). Export therefore yields
a **raw** labeled corpus.

Curation stays the user's, and it rides entirely on **tags** — there is deliberately *no*
system-defined quality concept. Quality is perspectival: an output that is good for one
purpose (say, distilling task X) is bad for another (evaluating task Y), so a single built-in
`good`/`bad` axis would be a false universal, and a dedicated flag would have the system
endorse a quality vocabulary it has no business defining. Its only gains over an ordinary tag
— a fixed enum and a default — are exactly that overreach. So the user applies free-form tags
(`good-for-distillation`, `wrong`, whatever fits their decision) and filters at export:
`export --tag <keep>` / `export --exclude-tag <drop>` (match-any include and exclude, with
exclude winning). A tag is metadata like any other — stored verbatim, never inferred, never
part of the key.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Roadmap](../ROADMAP.md)</sub>

</div>
