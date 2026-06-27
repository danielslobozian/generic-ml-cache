#!/usr/bin/env python3
"""Gateway probe server.

Listens on a local port, logs every inbound HTTP request as a JSON record to a
newline-delimited JSON file, then always returns 529 so the client does not
retry or cache the response.

Usage:
    python3 tools/gateway-probe/probe.py [--port 7777] [--log probe.jsonl]

Each line in the log file is a JSON object:
    {
        "ts":      "2026-06-25T10:00:00.123456",
        "client":  "127.0.0.1",
        "method":  "POST",
        "path":    "/v1/messages",
        "headers": { "content-type": "application/json", ... },
        "body":    { ... }   # parsed JSON, or raw string if not JSON
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gateway probe — log and reject every request")
    p.add_argument("--port", type=int, default=7777, help="port to listen on (default 7777)")
    p.add_argument("--log", default="probe.jsonl", help="output file (default probe.jsonl)")
    return p.parse_args()


_log_path: str = "probe.jsonl"


class ProbeHandler(BaseHTTPRequestHandler):

    def _handle(self) -> None:
        length = int(self.headers.get("content-length", 0))
        raw = self.rfile.read(length) if length > 0 else b""

        try:
            body = json.loads(raw) if raw else None
        except Exception:
            body = raw.decode("utf-8", errors="replace")

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "client": self.client_address[0],
            "method": self.command,
            "path": self.path,
            "headers": dict(self.headers),
            "body": body,
        }

        with open(_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        print(
            f"  {record['ts']}  {self.command} {self.path}"
            f"  [{self.headers.get('content-type', '')}]"
            f"  body={len(raw)}b",
            flush=True,
        )

        self.send_response(529)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_POST(self) -> None:
        self._handle()

    def do_GET(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def log_message(self, *_) -> None:
        pass  # suppress default stderr logging


def main() -> None:
    args = _parse_args()
    global _log_path
    _log_path = args.log

    server = HTTPServer(("127.0.0.1", args.port), ProbeHandler)
    print(f"probe listening on http://127.0.0.1:{args.port}")
    print(f"logging to {args.log}")
    print()
    print("env vars to try:")
    print(f"  ANTHROPIC_BASE_URL=http://127.0.0.1:{args.port}")
    print(f"  OPENAI_BASE_URL=http://127.0.0.1:{args.port}")
    print()
    print("Ctrl-C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
