# Security Policy

`generic-ml-cache` takes security seriously. It ships as five packages —
`generic-ml-cache-core` (hexagonal kernel), `generic-ml-cache-adapters` (infrastructure
adapters), `generic-ml-cache-bootstrap` (the composition root), `generic-ml-cache-cli`
(terminal client), and `generic-ml-cache-daemon` (local HTTP daemon) — and this policy
covers all five. Thank you for helping keep it and its users safe.

## Supported versions

Only the **latest released `1.x` version** of each package receives security fixes —
there are no long-term-support branches or backports. If you hit a security issue,
please first confirm it still reproduces on the most recent release or on `main`.

## Reporting a vulnerability

**Please do not open a public issue, pull request, or discussion for a security
vulnerability.** Public disclosure before a fix is available puts users at risk.

Instead, report it privately through GitHub:

1. Go to the **Security** tab of this repository.
2. Choose **Report a vulnerability** to open a private security advisory.
3. Describe the issue with enough detail to reproduce it — ideally the exact
   `gmlcache` command (or the library call), the adapter and client involved, and what
   you observed versus what you expected.

This routes the report privately to the maintainers without needing an email address,
and lets us discuss and fix the issue confidentially before any public disclosure. If
GitHub's private reporting is somehow unavailable to you, you may instead report the
repository or content to GitHub directly via
[GitHub's report abuse flow](https://github.com/contact/report-abuse).

### What to expect

This is a volunteer-maintained project, so there is no guaranteed response time, but
reports are taken seriously and reviewed as promptly as possible. If a report is
accepted, we will work on a fix, credit you in the release notes unless you prefer to
stay anonymous, and coordinate disclosure with you. If it is declined, we will explain
why.

## Security model and scope

It helps to know what this tool does and does not protect, so you can judge whether
something is a vulnerability or expected behavior.

The engine (in `generic-ml-cache-core`) launches external CLI clients (such as
`claude`, `codex`, or `cursor-agent`) as subprocesses and records or replays their
output; the `gmlcache` client and any embedding application drive it. A few properties
are central to its security posture:

- **Isolation is for correctness, not sandboxing.** The engine always runs a client in
  its own isolated working folder so that created and modified files can be attributed
  to the run. This is *not* a security sandbox. A client is an external program running
  with your user's permissions; it can do anything that program is capable of. Run only
  clients you trust.
- **The prime directive is an instruction, not an enforcement boundary.** At record
  time the engine injects a system prompt telling the client to stay within its folder.
  This is a best-effort guardrail, never a guarantee, and it is never persisted with the
  stored execution. Do not rely on it to contain untrusted input.
- **Stored executions may contain captured output.** A stored execution keeps the
  client's `stdout`, `stderr`, and any files it produced. If a run involved secrets or
  sensitive data, that data can end up in the store. By default the store lives in a
  per-user data directory, outside any project; if you relocate it into a shared or
  committed location, or share the store, review the captured output first and keep
  secret-bearing data out of version control.

Reports that amount to "an untrusted client or prompt was able to do something harmful"
are generally **expected behavior**, not vulnerabilities, because the tool does not
claim to sandbox clients. Reports about the cache itself — for example, checksum
collisions that cause a wrong cache hit, isolation that leaks files into the caller's
folder unexpectedly, or the prime directive being persisted with a stored execution —
are in scope and we want to hear about them.
