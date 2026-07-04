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
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from email.message import Message
from typing import Any, cast

from generic_ml_cache_core.common.errors import ProviderApiError, ProviderProtocolError

#: A network failure carries no HTTP status; ProviderApiError.status_code needs an
#: int, so we use 0 to mean "no response reached us".
_NO_STATUS = 0

#: A payload that broke its contract on an otherwise-OK transport is reported with
#: this status — "the response arrived, the body is the problem" (W19).
_TRANSPORT_OK = 200

#: Cap the body snippet carried on a ProviderProtocolError so a diagnostic log of a
#: garbage response is not flooded with the whole payload.
_MAX_BODY_SNIPPET = 500


def _body_snippet(raw: bytes | str) -> str:
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    return text if len(text) <= _MAX_BODY_SNIPPET else text[:_MAX_BODY_SNIPPET] + "…"


def _decode_json_object(raw: bytes, *, provider: str, status_code: int) -> dict[str, Any]:
    """Decode a JSON object from ``raw`` or raise :class:`ProviderProtocolError`.

    A 200 whose body is not UTF-8, is not JSON, or is JSON but not an object breaks
    the contract the caller relies on — translate it here so it never leaks a raw
    ``json.JSONDecodeError`` / ``UnicodeDecodeError`` past the boundary."""
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderProtocolError(
            provider=provider, status_code=status_code, body=_body_snippet(raw)
        ) from exc
    # A JSON scalar/array (non-object) is not a valid provider response either.
    if not isinstance(decoded, dict):
        raise ProviderProtocolError(
            provider=provider, status_code=status_code, body=_body_snippet(raw)
        )
    # decoded is a dict here; cast narrows the key/value types the caller expects.
    return cast("dict[str, Any]", decoded)


@contextmanager
def translate_protocol_errors(provider: str, response: dict[str, Any]) -> Generator[None]:
    """Translate a malformed-response field access — a missing or renamed provider
    field surfacing as ``KeyError`` / ``TypeError`` / ``IndexError`` / ``Attribute
    Error`` — into :class:`ProviderProtocolError`, so an adapter's response parsing
    never leaks a raw structural error past the boundary (W19)."""
    try:
        yield
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ProviderProtocolError(
            provider=provider,
            status_code=_TRANSPORT_OK,
            body=_body_snippet(json.dumps(response)),
        ) from exc


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
    network failure). A response that arrives but whose body is not a JSON object is
    translated to :class:`ProviderProtocolError` and never retried. ``sleep`` is
    injectable so tests need not wait."""
    attempt = 0
    while True:
        attempt += 1
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted provider endpoint, https)
                return _decode_json_object(resp.read(), provider=provider, status_code=resp.status)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if _is_retryable_status(exc.code) and attempt < retry.max_attempts:
                sleep(_delay(retry, attempt, _retry_after_seconds(exc.headers)))
                continue
            # Bound the upstream error body (grouped nit): a provider error envelope
            # can be large and occasionally echoes request material, so snippet it like
            # the ProviderProtocolError path rather than carrying the full payload.
            raise ProviderApiError(
                provider=provider, status_code=exc.code, body=_body_snippet(body)
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            # HTTPError is a URLError subclass but is handled above, so this is a real
            # network/timeout failure (connection refused, DNS, read timeout).
            if attempt < retry.max_attempts:
                sleep(_delay(retry, attempt, None))
                continue
            raise ProviderApiError(
                provider=provider, status_code=_NO_STATUS, body=str(exc)
            ) from exc
