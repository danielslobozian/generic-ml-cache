<div align="center">

# Cassette Schema Reference

<sub>Reference</sub>

<br>

[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)

</div>

---

> [!TIP]
> Reference pages are optimized for lookup. Start with the conceptual documents when you need background.

The cassette schema is JSON and versioned.

A simplified shape:

```json
{
  "schema_version": 2,
  "client": "adapter-name",
  "model": "model-name",
  "effort": "effort-or-empty",
  "input_checksum": "...",
  "input_data": {
    "context": "...",
    "prompt": "..."
  },
  "response": {
    "stdout": "...",
    "stderr": "...",
    "exit": 0,
    "files": [],
    "usage": {
      "input_tokens": 0,
      "output_tokens": 0,
      "cache_read_tokens": null,
      "cache_write_tokens": null,
      "reasoning_tokens": null,
      "cost_usd": null,
      "raw": {}
    }
  }
}
```

Unknown usage values are `null`, not zero. `raw` preserves adapter-provided usage
when available.

---

<div align="center">

<sub>[Documentation home](../README.md)&nbsp;&nbsp;•&nbsp;&nbsp;[Repository README](../../README.md)</sub>

</div>
