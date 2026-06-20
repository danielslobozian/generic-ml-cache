<div align="center">

# Future: API Adapters

<sub>Future direction</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!NOTE]
> This document describes planned direction. It should be read as design intent, not as a guarantee that the feature already exists.

API adapters should be peers to CLI adapters.

The engine should still receive an execution request and produce a cassette. The
adapter decides how to call the provider API, how to pass model/options, and how
to normalize usage.

Some grants that matter for local CLI clients may not apply to provider APIs.
Adapter support must be explicit.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
