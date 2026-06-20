<div align="center">

# Grants Reference

<sub>Reference</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!TIP]
> Reference pages are optimized for lookup. Start with the conceptual documents when you need background.

This document lists the common grant vocabulary and adapter support. The exact
support matrix should be verified against the current implementation before each
release.

## Current and planned common grants

| Grant | Meaning |
|---|---|
| `net` | Allow network/web access where the adapter supports it |
| `read` | Allow declared reads outside the isolated workspace |
| `write` | Allow writes in the execution workspace or declared output area |
| `shell` | Allow command execution where the adapter supports it |
| `web-search` | Allow explicit web-search tooling where distinct from network access |
| `mcp` | Future MCP access if adapter support is proven |
| `sub-agent` | Future spawned-agent access if adapter support is proven |

A grant should not be added to the common vocabulary merely because one adapter
has a unique flag. The shared grant name should have a clear cross-adapter
meaning.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
