<div align="center">

# Storage Model

<sub>Architecture</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

Storage separates structure from bytes:

1. The **execution repository** (SQLite) — the structured record of each execution
   (identity, kind, outcome, usage, and references to its output).
2. The **blob store** (content-addressed) — the output bytes, shared when identical.
3. The **access registry** (SQLite) — access events and hit counts, non-load-bearing.

The execution repository preserves what was recorded; the registry records access and
future scope/session/reporting relationships.

Bytes are addressed by content; folders are representation. The database is authority.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
