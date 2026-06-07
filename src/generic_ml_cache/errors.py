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
