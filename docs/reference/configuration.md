<div align="center">

# Configuration Reference

<sub>Reference</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!TIP]
> Reference pages are optimized for lookup. Start with the conceptual documents when you need background.

Configuration is resolved with clear precedence. The exact supported keys depend
on the installed version.

Typical settings include:

- default mode,
- store path,
- timeout,
- max cache size,
- executable paths,
- scan trust,
- grants defaults where appropriate.

## max_size

`max_size` enables insertion-time size eviction. It is off by default.

When configured, the store evicts least-recently-used cassettes to make room for a
new cassette. See [Cache eviction](../concepts/cache-eviction.md).

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
