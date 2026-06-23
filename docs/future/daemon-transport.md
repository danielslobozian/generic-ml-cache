<div align="center">

# Future: Daemon Transport

<sub>Future direction</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!NOTE]
> This document describes planned direction. It should be read as design intent, not as a guarantee that the feature already exists.

Daemon mode should expose the same single-user engine through a resident **local** process —
another *interface* over the same cache, never another engine and never a multi-user service.
"Callers" here means your own tools and scripts on your own machine, not several people.

It should not create a separate cache model.

The daemon can add:

- live event delivery,
- a local HTTP / IPC API,
- shared process state across your own tools,
- a single place to watch and replay.

## Local gateway (diagnostic)

A resident process opens a useful, strictly-local possibility: point **your own** ML client at
the daemon and let it sit in front of the real client as a pass-through, so every call the
client makes under the hood is intercepted, cached, and traced. A single interactive session
often fans out into far more provider calls than it looks like; routing them through the daemon
lets you see exactly **how many calls, of what shape, at what token cost** — and which basic
steps are worth lifting out into plain, deterministic code.

This stays inside the positioning: it is **local, single-user observability of your own
tooling**. Using a gateway to front API calls you own is fine; using one to put a subscription
seat behind several people is not — see [Positioning](../design/positioning.md). The
equivalence test for any such pass-through: the result must be identical whether it goes
through the daemon or not — it only observes and caches, never changes the answer.

The underlying execution concepts remain execution request, adapter, execution record,
session, and report.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
