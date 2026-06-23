# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Exception types raised by generic-ml-cache."""

from __future__ import annotations


class CacheError(Exception):
    """Base class for all generic-ml-cache errors."""


class CacheMiss(CacheError):
    """Raised in offline mode when no stored execution matches the request.

    Offline mode is a *knowing* switch to replay-only: a miss is an error, never
    a silent fall-through to a real call.
    """


class UnknownClient(CacheError):
    """Raised when no adapter is registered for the requested client name."""


class ConfigError(CacheError):
    """Raised when the optional config file or a config env var is invalid.

    A missing config file is never an error -- it just means built-in defaults
    apply. This is only for a file that exists but cannot be parsed, or a value
    (mode, timeout) that is not understood.
    """


class ClientNotFound(CacheError):
    """Raised when the client executable cannot be located on the system."""


class CommandLineTooLong(CacheError):
    """Raised before launch when the assembled command line would exceed the
    operating system's argument-size limit.

    Only a client that receives the prompt as a command-line argument
    (cursor-agent, which has no stdin path) can hit this; claude and codex take the
    prompt on stdin and are unaffected. Raising it up front turns an opaque OS
    "argument list too long" error (or a silent Windows failure) into a clear
    message that names the size, the limit, and the remedy.
    """


class InputFileError(CacheError):
    """Raised when a declared input file cannot be read for fingerprinting.

    The path does not point to a regular file, or the bytes could not be read.
    The filesystem fingerprint adapter translates the foreign ``OSError`` into
    this cause-named exception so the core never sees a library error type.
    """


class ArtifactBlobMissing(CacheError):
    """Raised when hydrating an execution whose artifact references a blob that
    the blob store no longer holds.

    The structured record says the output was persisted, but the bytes are gone
    (an out-of-band deletion, a half-completed prune). The engine fails loud
    rather than returning a silently empty result.
    """


class WrongEncryptionToken(CacheError):
    """Raised when a token cannot decrypt the store's wrapped data key.

    The token is wrong (or the wrapped key was tampered with): the authenticated
    decryption of the key envelope failed. The cipher adapter translates the
    library's integrity error into this cause-named exception so the core never
    sees a foreign error type, and the caller can offer "provide the right token
    or invalidate" rather than leaking a stack trace.
    """


class EncryptionTokenRequired(CacheError):
    """Raised when an operation needs to read or write encrypted content but no
    token was supplied.

    The store is globally encrypted, so there is no plaintext fallback: reading a
    hit or recording a new entry needs the token. Metadata-only operations (list,
    stats, tags, status) do not touch content and still work without it.
    """


class EncryptionStateError(CacheError):
    """Raised when an encryption operation does not match the store's state —
    enabling an already-encrypted store, or disabling/rotating a public one.
    """


class StoreLocked(CacheError):
    """Raised when an exclusive store operation cannot start because another
    process already holds the store lock.

    The lock makes the store immutable during an encryption migration
    (enable/disable). It is an OS-level lock that releases automatically when the
    holding process dies, so there is never a stale lock to clear by hand;
    acquisition fails fast rather than blocking.
    """


class RunInterrupted(Exception):
    """Raised when a real client run is stopped by a signal from the caller (the
    workflow engine) before it finished.

    Deliberately **not** a ``CacheError``: it is not a fault but a requested stop,
    and it must never be recorded as an execution -- an interrupted call is not a
    result. The CLI maps it to a distinct exit code so a stop is distinguishable
    from a failure.
    """
