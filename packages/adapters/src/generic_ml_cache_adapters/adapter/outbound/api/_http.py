# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Shared HTTP request + retry helper for the direct API adapters (G-1/V29).

One place that performs a JSON request over stdlib ``urllib`` and, on a *retryable*
failure, backs off and retries — so the three provider adapters do not each
re-implement it. Retry policy: 429 + 5xx + network/timeout only, NEVER other 4xx
(a bad request or auth failure will not fix itself). Exponential backoff with full
jitter, bounded by ``max_attempts``, honouring a numeric ``Retry-After`` header when
the server sends one. stdlib only (no ``tenacity`` — dependency discipline). The
caching gateway's own retry is a separate concern and is not wired here.

This also owns the §10 boundary translation (``urllib.error.HTTPError`` /network
error -> ``ProviderApiError``), so a caller never sees a leaked urllib type.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from email.message import Message
from typing import Any

from generic_ml_cache_core.common.errors import ProviderApiError

#: A network failure carries no HTTP status; ProviderApiError.status_code needs an
#: int, so we use 0 to mean "no response reached us".
_NO_STATUS = 0


@dataclass(frozen=True)
class RetryPolicy:
    """How the API adapters retry a failed request. Defaults suit a synchronous
    single call: three attempts, half-second base, capped at eight seconds."""

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0


#: The shipped default (frozen, so a shared singleton is safe as an argument default).
_DEFAULT_RETRY = RetryPolicy()


def _is_retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def _retry_after_seconds(headers: Message | None) -> float | None:
    """The numeric ``Retry-After`` (seconds) if present and parseable; the HTTP-date
    form is not honoured (we fall back to backoff)."""
    if headers is None:
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(int(raw))
    except ValueError:
        return None


def _delay(policy: RetryPolicy, attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(retry_after, policy.max_delay)
    ceiling = min(policy.max_delay, policy.base_delay * (2 ** (attempt - 1)))
    return random.uniform(0.0, ceiling)  # full jitter — spread out concurrent retries


def request_json(
    req: urllib.request.Request,
    *,
    provider: str,
    timeout: float,
    retry: RetryPolicy = _DEFAULT_RETRY,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Perform ``req`` and return the parsed JSON object, retrying retryable failures.

    On a non-retryable HTTP status (any 4xx but 429) or after the last attempt, the
    foreign error is translated to :class:`ProviderApiError` (status ``0`` for a
    network failure). ``sleep`` is injectable so tests need not wait."""
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted provider endpoint, https)
                parsed: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                return parsed
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if _is_retryable_status(exc.code) and attempt < retry.max_attempts:
                sleep(_delay(retry, attempt, _retry_after_seconds(exc.headers)))
                continue
            raise ProviderApiError(provider=provider, status_code=exc.code, body=body) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            # HTTPError is a URLError subclass but is handled above, so this is a real
            # network/timeout failure (connection refused, DNS, read timeout).
            if attempt < retry.max_attempts:
                sleep(_delay(retry, attempt, None))
                continue
            raise ProviderApiError(
                provider=provider, status_code=_NO_STATUS, body=str(exc)
            ) from exc
