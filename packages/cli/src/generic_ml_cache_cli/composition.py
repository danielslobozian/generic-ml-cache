# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Composition root helpers — shared wiring and resolution utilities used by all controllers."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from pathlib import Path
from typing import cast

from generic_ml_cache_adapters.adapter.out.diagnostics.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_adapters.adapter.out.diagnostics.structlog_diagnostics_adapter import (
    StructlogDiagnosticsAdapter,
)
from generic_ml_cache_adapters.datasource import sqlite_connection_factory
from generic_ml_cache_adapters.db import DbConnection
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from generic_ml_cache_core.common.errors import ConfigError

from generic_ml_cache_cli._compose import build_store_encryptor, load_cipher

from . import config

_DB_NAME = "executions.sqlite3"


def _db_conn_factory(store_root: Path) -> Callable[[], DbConnection]:
    # The library's canonical factory: it creates the parent dir and, crucially,
    # sets PRAGMA foreign_keys = ON per connection so the schema's FKs are enforced.
    return cast("Callable[[], DbConnection]", sqlite_connection_factory(store_root / _DB_NAME))


def _make_diag(args: argparse.Namespace) -> DiagnosticsPort:
    """Build the DiagnosticsPort from resolved settings.

    Precedence: --log-level flag > GMLCACHE_LOG_LEVEL env > config key > off (quiet).
    Log file:   --log-file flag  > GMLCACHE_LOG_FILE env  > config key > <store>/gmlcache.log.
    """
    level: str | None = getattr(args, "log_level", None)
    log_file_flag: str | None = getattr(args, "log_file", None)
    try:
        settings = config.resolve_settings(
            config.load(),
            log_level_flag=level,
            log_file_flag=log_file_flag,
        )
    except Exception:  # noqa: BLE001 — logging is non-load-bearing; bad config → silent (null) diag
        return NullDiagnosticsAdapter()
    resolved_level = settings["log_level"][0]
    if not resolved_level:
        return NullDiagnosticsAdapter()
    log_file = Path(str(settings["log_file"][0]))
    log_file.parent.mkdir(parents=True, exist_ok=True)
    return StructlogDiagnosticsAdapter(log_file, level=str(resolved_level))


def _store_root() -> Path | None:
    try:
        return Path(str(config.resolve_settings(config.load())["store"][0]))
    except ConfigError as exc:
        import sys

        print(f"gmlc: {exc}", file=sys.stderr)
        return None


def _resolve_token(args: argparse.Namespace) -> str | None:
    """The encryption token for this call: the --token flag, else GMLCACHE_TOKEN.
    A token is a secret, so it is never read from the config file."""
    flag = getattr(args, "token", None)
    return flag if flag else (os.environ.get("GMLCACHE_TOKEN") or None)


def _resolve_session(args: argparse.Namespace) -> str | None:
    """The session id for this run: the --session flag, else GMLCACHE_SESSION. A session
    groups a workflow's calls; it is journal metadata, never part of the cache key."""
    flag = getattr(args, "session", None)
    return flag if flag else (os.environ.get("GMLCACHE_SESSION") or None)


def _read_text_arg(inline: str | None, path: str | None, name: str) -> str:
    if inline is not None and path is not None:
        raise SystemExit(f"error: pass only one of --{name} / --{name}-file")
    if path is not None:
        return Path(path).read_text(encoding="utf-8")
    return inline if inline is not None else ""


def _resolve_input_file_paths(raw_paths) -> list[str]:
    """Declared input files, resolved to absolute (path-sensitive keying). The
    use case's fingerprint adapter validates readability and raises on a bad one."""
    return [str(Path(raw).resolve()) for raw in (raw_paths or [])]


def _resolve_allow_paths(raw_paths) -> list[str]:
    """Declared scan folders: validated directories, normalised to absolute."""
    resolved: list[str] = []
    for raw in raw_paths or []:
        path = Path(raw)
        if not path.is_dir():
            raise SystemExit(f"error: allow-path is not a directory: {raw}")
        resolved.append(str(path.resolve()))
    return resolved


def _load_cipher():
    return load_cipher()


def _store_encryptor(store_root: Path, cipher=None):
    return build_store_encryptor(store_root, cipher)
