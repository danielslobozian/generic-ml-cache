<div align="center">

# Cassettes

<sub>Concepts</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

## At a glance

- [Contents](#contents)
- [Generated files](#generated-files)
- [Usage metadata](#usage-metadata)

---

A cassette is an immutable record of a successful detached execution.

It contains enough information to inspect the execution and replay its observable
result without calling the underlying adapter again.

## Contents

A cassette records:

- adapter/client,
- model,
- effort,
- execution request checksum,
- prompt/context data or checksums,
- stdout,
- stderr,
- exit code,
- generated files,
- usage metadata when available,
- schema version.

## Generated files

Generated files are first-class cassette content.

A detached ML call may produce useful work by writing files rather than printing
to stdout. Caching only stdout would lose that work. gmlcache therefore records
files created or modified inside the isolated execution folder and can replay or
materialize them later.

## Usage metadata

Cassettes can include normalized usage fields and the adapter’s raw usage block.
Unknown values remain unknown. Client-reported cost is recorded as an estimate,
not authoritative billing.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
