# On-disk layout

Everything the cache stores lives in one **store directory**. Its location is set
only by the config file's `store` key (or the built-in per-user default,
`~/.local/share/generic-ml-cache/cassettes`, honoring `XDG_DATA_HOME`); there is no
flag or environment override for it, because the store is the cache's own
structure, not a per-call knob.

The directory is flat and contains two kinds of entry:

```
<store>/
  3f9a…b2.json        a recorded call (one per cassette)
  7c41…e8.json
  …
  registry.sqlite3    the access registry (side log)
```

## Cassettes — `<match_key>.json`

One file per recorded call. The filename is the **match-key digest**, so a lookup
is a direct O(1) file check; the file *contents* repeat the readable fields so any
cassette is fully inspectable on its own (`gmlcache inspect <file>`):

- `client` / `model` / `effort`
- `input_data` — the `context`, the `prompt`, and checksums of any declared input
  files (content, not paths, is what the key is built from)
- `response` — `stdout`, `stderr`, `exit`, and any files the call created in its
  isolated run folder
- `schema_version`

Cassettes are **write-once and read-only**. A cassette is built entirely in memory
and only written once the keep decision is made, in a single atomic step (temp file
then replace), and is then marked read-only on disk. A cache hit is a pure read and
never writes back into it. Read-only is a best-effort deterrent against a stray
edit, not a guarantee — the file is in a directory you control.

You can copy or read a cassette freely. Deleting one by hand just means the next
identical call records it again (and leaves its rows in the registry orphaned —
prefer letting size eviction handle space, or wipe the whole directory for a clean
reset).

## Access registry — `registry.sqlite3`

A small SQLite log (stdlib `sqlite3`, no dependency) of access events — `hit`,
`miss`, `record`, `evict` — read by `stats` and by size eviction (for
least-recently-used ordering).

It is **non-load-bearing**: the cache resolves calls correctly whether or not it
exists. Deleting it is safe — you only lose access history and stats, and LRU
ordering falls back to file age until the log rebuilds. It records access only; it
holds no integrity/checksum role (a checksum kept beside the data it guards, in a
directory you can write, would protect nothing).

## Transient files

During a write the cache may briefly create a `<key>.json.<pid>.tmp` file, which it
removes on success or on any failure. A crash at the wrong instant could rarely
leave one behind; it is harmless and ignored (lookups and `stats` only read
`*.json`).

## Wiping the cache

Delete the whole store directory. Cassettes and the registry both live inside it,
so removing the directory clears everything cleanly with nothing orphaned; the
cache recreates what it needs on the next call.
