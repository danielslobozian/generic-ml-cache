# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: encryption commands — encrypt, decrypt, rotate, invalidate."""

from __future__ import annotations

import argparse
import sys

from generic_ml_cache_core.common.errors import (
    EncryptionStateError,
    StoreLocked,
    WrongEncryptionToken,
)

from generic_ml_cache_cli.composition import (
    _load_cipher,
    _resolve_token,
    _store_encryptor,
    _store_root,
)


def _cmd_encrypt(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    cipher = _load_cipher()
    token = cipher.generate_token()
    try:
        _store_encryptor(store_root, cipher).enable(token)
    except (EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("encryption enabled. Save this token — it is shown once and cannot be recovered:")
    print(f"\n    {token}\n")
    print("Pass it with --token or GMLCACHE_TOKEN to read or write this store.")
    return 0


def _cmd_decrypt(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    token = _resolve_token(args)
    if not token:
        print("gmlc: provide the token with --token or GMLCACHE_TOKEN", file=sys.stderr)
        return 4
    try:
        _store_encryptor(store_root, _load_cipher()).disable(token)
    except (WrongEncryptionToken, EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("encryption disabled. The store is now public; no token is needed.")
    return 0


def _cmd_rotate(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    old_token = _resolve_token(args)
    if not old_token:
        print("gmlc: provide the current token with --token or GMLCACHE_TOKEN", file=sys.stderr)
        return 4
    cipher = _load_cipher()
    new_token = cipher.generate_token()
    try:
        _store_encryptor(store_root, cipher).rotate(old_token, new_token)
    except (WrongEncryptionToken, EncryptionStateError, StoreLocked) as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("token rotated. Save the new token — it is shown once:")
    print(f"\n    {new_token}\n")
    return 0


def _cmd_invalidate(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    if not args.yes:
        print(
            "gmlc: this permanently wipes the cache (crypto-shred) and cannot be undone. "
            "Re-run with --yes to confirm.",
            file=sys.stderr,
        )
        return 4
    try:
        _store_encryptor(store_root).invalidate()  # no token needed
    except StoreLocked as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4
    print("store invalidated: the cache was wiped and is now empty and public.")
    return 0
