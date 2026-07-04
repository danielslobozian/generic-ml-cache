# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: encryption commands — encrypt, decrypt, rotate, invalidate."""

from __future__ import annotations

import argparse
import sys

from generic_ml_cache_bootstrap.encryption import StoreEncryptionOps
from generic_ml_cache_core.common.errors import (
    EncryptionStateError,
    StoreLocked,
    WrongEncryptionToken,
)

from generic_ml_cache_cli.composition import resolve_token, store_root

# Shown when a token-minting command runs but the optional `[encryption]` extra
# (the `cryptography` dependency) is not installed. The facade raises a bare
# ImportError; this is the CLI's user-facing translation of it.
_ENCRYPTION_EXTRA_ERROR = (
    "error: encryption needs an optional dependency — install with "
    '`pip install "generic-ml-cache-adapters[encryption]"`'
)


def cmd_encrypt(_args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    try:
        token = StoreEncryptionOps(store_root_path).enable()
    except (EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    except ImportError as exc:  # pragma: no cover — needs the [encryption] extra absent
        raise SystemExit(_ENCRYPTION_EXTRA_ERROR) from exc
    print("encryption enabled. Save this token — it is shown once and cannot be recovered:")
    print(f"\n    {token}\n")
    print("Pass it with --token or GMLCACHE_TOKEN to read or write this store.")
    return 0


def cmd_decrypt(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    token = resolve_token(args)
    if not token:
        print("gmlc: provide the token with --token or GMLCACHE_TOKEN", file=sys.stderr)
        return 4
    try:
        StoreEncryptionOps(store_root_path).disable(token)
    except (WrongEncryptionToken, EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    except ImportError as exc:  # pragma: no cover — needs the [encryption] extra absent
        raise SystemExit(_ENCRYPTION_EXTRA_ERROR) from exc
    print("encryption disabled. The store is now public; no token is needed.")
    return 0


def cmd_rotate(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    old_token = resolve_token(args)
    if not old_token:
        print("gmlc: provide the current token with --token or GMLCACHE_TOKEN", file=sys.stderr)
        return 4
    try:
        new_token = StoreEncryptionOps(store_root_path).rotate(old_token)
    except (WrongEncryptionToken, EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    except ImportError as exc:  # pragma: no cover — needs the [encryption] extra absent
        raise SystemExit(_ENCRYPTION_EXTRA_ERROR) from exc
    print("token rotated. Save the new token — it is shown once:")
    print(f"\n    {new_token}\n")
    return 0


def cmd_invalidate(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    if not args.yes:
        print(
            "gmlc: this permanently wipes the cache (crypto-shred) and cannot be undone. "
            "Re-run with --yes to confirm.",
            file=sys.stderr,
        )
        return 4
    try:
        StoreEncryptionOps(store_root_path).invalidate()  # no token needed
    except StoreLocked as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("store invalidated: the cache was wiped and is now empty and public.")
    return 0
