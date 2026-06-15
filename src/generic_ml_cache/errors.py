# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Exception types raised by generic-ml-cache."""

from __future__ import annotations


class CacheError(Exception):
    """Base class for all generic-ml-cache errors."""


class CacheMiss(CacheError):
    """Raised in offline mode when no cassette matches the request.

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


class CassetteFormatError(CacheError):
    """Raised when a cassette file on disk is malformed or unreadable."""


class IsolationViolation(CacheError):
    """Raised when a recorded run reported touching files outside its folder.

    Hard isolation (containers, chroot) is out of scope for v0.0.1; this surfaces
    the *soft* signal a well-behaved client emits when the prime directive is
    violated.
    """


class RunInterrupted(Exception):
    """Raised when a real client run is stopped by a signal from the caller (the
    workflow engine) before it finished.

    Deliberately **not** a ``CacheError``: it is not a fault but a requested stop,
    and it must never be recorded as a cassette -- an interrupted call is not a
    result. The CLI maps it to a distinct exit code so a stop is distinguishable
    from a failure.
    """
