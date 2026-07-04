# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Exception types raised by generic-ml-cache."""

from __future__ import annotations

from typing import ClassVar


class CacheError(Exception):
    """Base class for all generic-ml-cache errors."""

    code: ClassVar[str] = "cache.error"


class CacheMiss(CacheError):
    """Raised in offline mode when no stored execution matches the request.

    Offline mode is a *knowing* switch to replay-only: a miss is an error, never
    a silent fall-through to a real call.
    """

    code: ClassVar[str] = "cache.miss"


class UnknownClient(CacheError):
    """Raised when no adapter is registered for the requested client name."""

    code: ClassVar[str] = "adapter.unknown"


class CapabilityUnavailable(CacheError):
    """Raised when no adapter for a client offers a required capability
    (e.g. asking for model listing from a client that cannot enumerate models).
    """

    code: ClassVar[str] = "adapter.capability_unavailable"


class ConfigError(CacheError):
    """Raised when the optional config file or a config env var is invalid.

    A missing config file is never an error -- it just means built-in defaults
    apply. This is only for a file that exists but cannot be parsed, or a value
    (mode, timeout) that is not understood.
    """

    code: ClassVar[str] = "config.invalid"


class ClientNotFound(CacheError):
    """Raised when the client executable cannot be located on the system."""

    code: ClassVar[str] = "adapter.not_found"


class CommandLineTooLong(CacheError):
    """Raised before launch when the assembled command line would exceed the
    operating system's argument-size limit.

    Only a client that receives the prompt as a command-line argument
    (cursor-agent, which has no stdin path) can hit this; claude and codex take the
    prompt on stdin and are unaffected. Raising it up front turns an opaque OS
    "argument list too long" error (or a silent Windows failure) into a clear
    message that names the size, the limit, and the remedy.
    """

    code: ClassVar[str] = "adapter.command_too_long"


class InputFileError(CacheError):
    """Raised when a declared input file cannot be read for fingerprinting.

    The path does not point to a regular file, or the bytes could not be read.
    The filesystem fingerprint adapter translates the foreign ``OSError`` into
    this cause-named exception so the core never sees a library error type.
    """

    code: ClassVar[str] = "input.file_error"


class ArtifactBlobMissing(CacheError):
    """Raised when hydrating an execution whose artifact references a blob that
    the blob store no longer holds.

    The structured record says the output was persisted, but the bytes are gone
    (an out-of-band deletion, a half-completed prune). The engine fails loud
    rather than returning a silently empty result.
    """

    code: ClassVar[str] = "store.blob_missing"


class WrongEncryptionToken(CacheError):
    """Raised when a token cannot decrypt the store's wrapped data key.

    The token is wrong (or the wrapped key was tampered with): the authenticated
    decryption of the key envelope failed. The cipher adapter translates the
    library's integrity error into this cause-named exception so the core never
    sees a foreign error type, and the caller can offer "provide the right token
    or invalidate" rather than leaking a stack trace.
    """

    code: ClassVar[str] = "crypto.wrong_token"


class EncryptionTokenRequired(CacheError):
    """Raised when an operation needs to read or write encrypted content but no
    token was supplied.

    The store is globally encrypted, so there is no plaintext fallback: reading a
    hit or recording a new entry needs the token. Metadata-only operations (list,
    stats, tags, status) do not touch content and still work without it.
    """

    code: ClassVar[str] = "crypto.token_required"


class EncryptionStateError(CacheError):
    """Raised when an encryption operation does not match the store's state —
    enabling an already-encrypted store, or disabling/rotating a public one.
    """

    code: ClassVar[str] = "crypto.state_error"


class StoreLocked(CacheError):
    """Raised when an exclusive store operation cannot start because another
    process already holds the store lock.

    The lock makes the store immutable during an encryption migration
    (enable/disable). It is an OS-level lock that releases automatically when the
    holding process dies, so there is never a stale lock to clear by hand;
    acquisition fails fast rather than blocking.
    """

    code: ClassVar[str] = "store.locked"


class UnsupportedExecutionMode(CacheError):
    """Raised when a local client adapter does not support the requested
    execution mode (e.g. asking a passthrough-only adapter to run managed).

    The adapter declares its supported modes via ``supports(kind)``. The core
    checks capability before dispatching so the caller gets a clear, named error
    rather than a silent wrong-mode execution.
    """

    code: ClassVar[str] = "adapter.unsupported_mode"


class MigrationFailed(CacheError):
    """Raised when a database schema migration fails and is rolled back.

    Translates a raw DBAPI/driver error at the migration boundary into the
    project's own vocabulary (§10), so a caller never sees a leaked ``sqlite3``
    exception. The failed migration leaves the recorded schema version unchanged —
    the next startup retries from the last good state.
    """

    code: ClassVar[str] = "store.migration_failed"


class PersistenceContractOutdated(CacheError):
    """Raised at startup when an injected persistence adapter implements an older
    model contract than this build requires (C-2).

    The whole-store version handshake: bootstrap compares the adapter's
    ``implemented_version()`` against core's ``CURRENT_MODEL_VERSION`` and refuses
    to serve when the adapter is behind, rather than letting a stale mapping
    silently write ``NULL`` for a field it does not know about. Preventive and
    fail-fast (Flyway / Hibernate-``validate`` at boot) — the message tells the
    embedder which version to upgrade their adapter to.
    """

    code: ClassVar[str] = "store.contract_outdated"


class ProviderApiError(CacheError):
    """Raised when a provider's HTTP API returns an error response (G-1/V28, §10).

    Translates the foreign ``urllib.error.HTTPError`` at the API-adapter boundary
    into the project's own vocabulary, so a caller never sees a leaked urllib type.
    Carries the ``provider`` name, HTTP ``status_code``, and response ``body`` — the
    status code lets the retry policy (V29) decide retryability (429/5xx retryable,
    4xx not), and the body is preserved for diagnostics. Java: Spring
    ``RestClientResponseException`` / ``DataAccessException`` translation.
    """

    code: ClassVar[str] = "provider.api_error"

    def __init__(self, provider: str, status_code: int, body: str) -> None:
        self.provider = provider
        self.status_code = status_code
        self.body = body
        super().__init__(f"{provider} API error {status_code}: {body}")


class ProviderProtocolError(ProviderApiError):
    """Raised when a provider's transport SUCCEEDED (a response arrived) but the
    PAYLOAD broke its contract: undecodable or malformed JSON, a non-object body,
    or a field the adapter needs that is missing or renamed.

    Distinct from its parent ``ProviderApiError`` (an HTTP *status* error): here the
    status is fine but the body cannot be trusted, so it is never retried (a bad
    payload will not fix itself). Inherits ``provider`` / ``status_code`` / ``body``;
    the body is a BOUNDED snippet, not the full payload, so a diagnostic log is not
    flooded. Java: a Jackson ``JsonMappingException`` translated at the client
    boundary, as opposed to an ``HttpClientErrorException`` for a 4xx/5xx.
    """

    code: ClassVar[str] = "provider.protocol_error"


class StoreConsistencyError(CacheError):
    """Raised when a DB-first write targets an execution that is not there to
    update — a ``mark_artifacts_*`` / ``finalize`` for an ``execution_id`` with no
    matching row, or a ``finalize`` while some artifact is not yet STORED.

    In the correct flow this never happens (the row was just inserted and every
    artifact marked before finalize). Surfacing it loudly instead of silently
    updating zero rows is the whole point of W1: a mistargeted write must fail,
    not corrupt the cache in silence. Java: an optimistic-lock / ``@Version``
    mismatch surfacing as ``OptimisticLockException`` rather than a lost update.
    """

    code: ClassVar[str] = "store.consistency"


class RunInterrupted(Exception):
    """Raised when a real client run is stopped by a signal from the caller (the
    workflow engine) before it finished.

    Deliberately **not** a ``CacheError``: it is not a fault but a requested stop,
    and it must never be recorded as an execution -- an interrupted call is not a
    result. The CLI maps it to a distinct exit code so a stop is distinguishable
    from a failure.
    """
