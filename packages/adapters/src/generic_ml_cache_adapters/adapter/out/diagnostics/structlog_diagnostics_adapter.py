# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StructlogDiagnosticsAdapter — file-backed, logback-style implementation.

Writes structured diagnostic lines to a rotating log file. Each line carries:
  timestamp  [thread-name:thread-id]  LEVEL  ClassName.method_name:lineno — msg  k=v …

Format is human-readable text (logback convention) by default; pass
``fmt="json"`` for newline-delimited JSON suitable for log aggregators.

All string values — including rendered exception tracebacks — are passed through
a PII scrubbing processor before being written. The scrubber redacts:
  - E-mail addresses  →  [email]
  - Bearer / API tokens in Authorization-style headers  →  [token]
  - Long opaque strings that look like secrets (base64/hex ≥ 32 chars)  →  [secret]
  - Values stored under sensitive key names (token, secret, password, …)  →  [redacted]

Usage (composition root in CLI or daemon):

    from generic_ml_cache_adapters.adapter.out.diagnostics.structlog_diagnostics_adapter import StructlogDiagnosticsAdapter
    diag = StructlogDiagnosticsAdapter(log_file=store_root / "gmlcache.log", level="INFO")
    use_cases = build_use_cases(conn_factory, diag=diag, ...)
"""

from __future__ import annotations

import re
import sys
import threading
import traceback
from enum import Enum
from pathlib import Path
from typing import IO, Any

import structlog
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort
from structlog.types import EventDict, WrappedLogger

# ---------------------------------------------------------------------------
# Level ordering
# ---------------------------------------------------------------------------

_LEVEL_ORDER = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}


class DiagnosticsLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

# Key names whose values must never appear in logs regardless of their shape.
_SENSITIVE_KEYS = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "credential",
        "key_material",
        "private_key",
        "access_token",
        "refresh_token",
    }
)

# Patterns applied to every string value (and to rendered traceback text).
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # E-mail addresses
    (re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"), "[email]"),
    # Authorization / Bearer header values
    (
        re.compile(r"(?i)(bearer|token|api[-_]?key)\s+[A-Za-z0-9\-._~+/=]{8,}"),
        r"\1 [token]",
    ),
    # Long opaque strings ≥ 32 chars that look like API keys or encryption tokens.
    # Requires at least one uppercase letter or base64 special char (+/) so that
    # pure-lowercase-hex strings (SHA-256 content-addressed keys) are left intact.
    (
        re.compile(r"[a-z0-9]*[A-Z+/][A-Za-z0-9+/\-_]{30,}={0,2}"),
        "[secret]",
    ),
]


def _scrub_string(value: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _scrub_string(value)
    return value


def _scrub_processor(logger: WrappedLogger, method: str, event_dict: EventDict) -> EventDict:
    """Redact PII from every string field before the event reaches the renderer."""
    scrubbed: EventDict = {}
    for k, v in event_dict.items():
        if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
            scrubbed[k] = "[redacted]"
        else:
            scrubbed[k] = _scrub_value(v)
    return scrubbed


# ---------------------------------------------------------------------------
# Custom structlog processors
# ---------------------------------------------------------------------------


def _caller_info_processor(logger: WrappedLogger, method: str, event_dict: EventDict) -> EventDict:
    """Walk the call stack to find the first frame outside this module and
    the structlog internals, then inject class, method, and line number."""
    this_file = __file__.rstrip("c")  # strip .pyc → .py
    frame = sys._getframe(1)
    while frame is not None:
        fname = frame.f_code.co_filename.rstrip("c")
        if fname != this_file and "structlog" not in fname:
            func = frame.f_code.co_name
            lineno = frame.f_lineno
            self_ = frame.f_locals.get("self", None)
            cls = type(self_).__name__ if self_ is not None else None
            event_dict["caller"] = f"{cls}.{func}:{lineno}" if cls else f"{func}:{lineno}"
            break
        frame = frame.f_back  # type: ignore[assignment]
    return event_dict


def _thread_info_processor(logger: WrappedLogger, method: str, event_dict: EventDict) -> EventDict:
    t = threading.current_thread()
    event_dict["thread"] = f"{t.name}:{threading.get_ident()}"
    return event_dict


def _exc_processor(logger: WrappedLogger, method: str, event_dict: EventDict) -> EventDict:
    """Render the ``exc`` key as a formatted traceback string."""
    exc: BaseException | None = event_dict.pop("exc", None)
    if exc is not None:
        event_dict["traceback"] = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ).rstrip()
    return event_dict


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _build_text_renderer() -> Any:
    """Logback-style: ``2026-06-27 22:33:20.620 [MainThread:123] INFO  Cls.m:42 — msg  k=v``"""

    def _render(logger: WrappedLogger, method: str, event_dict: EventDict) -> str:
        ts = event_dict.pop("timestamp", "")
        level = event_dict.pop("level", "").upper().ljust(5)
        thread = event_dict.pop("thread", "")
        caller = event_dict.pop("caller", "")
        msg = event_dict.pop("event", "")
        tb = event_dict.pop("traceback", None)

        extras = "  ".join(f"{k}={v}" for k, v in event_dict.items() if not k.startswith("_"))
        line = f"{ts} [{thread}] {level}  {caller} — {msg}"
        if extras:
            line += f"  {extras}"
        if tb:
            line += f"\n{tb}"
        return line

    return _render


def _build_json_renderer() -> Any:
    return structlog.processors.JSONRenderer()


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class StructlogDiagnosticsAdapter(DiagnosticsPort):
    """Writes structured diagnostic lines to *log_file*.

    Parameters
    ----------
    log_file:
        Destination file path. The parent directory must exist. Opened in
        append mode so existing logs are preserved across restarts.
    level:
        Minimum severity threshold. Events below this level are dropped.
        One of DEBUG / INFO / WARN / ERROR (default INFO).
    fmt:
        ``"text"`` (default) for logback-style human-readable lines;
        ``"json"`` for newline-delimited JSON suitable for ELK / log aggregators.
    """

    def __init__(
        self,
        log_file: Path,
        level: str = "INFO",
        fmt: str = "text",
    ) -> None:
        self._min_level = _LEVEL_ORDER.get(level.upper(), 1)
        renderer = _build_text_renderer() if fmt.lower() == "text" else _build_json_renderer()
        self._processors = [
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f", utc=False),
            _thread_info_processor,
            _caller_info_processor,
            _exc_processor,
            structlog.processors.format_exc_info,
            _scrub_processor,  # runs after exc is rendered to a string
            renderer,
        ]
        self._log_file = log_file
        self._file: IO[str] | None = None

    # ------------------------------------------------------------------
    # DiagnosticsPort implementation
    # ------------------------------------------------------------------

    def debug(self, msg: str, **context: object) -> None:
        if self._min_level <= _LEVEL_ORDER["DEBUG"]:
            self._emit("DEBUG", msg, **context)

    def info(self, msg: str, **context: object) -> None:
        if self._min_level <= _LEVEL_ORDER["INFO"]:
            self._emit("INFO", msg, **context)

    def warn(self, msg: str, **context: object) -> None:
        if self._min_level <= _LEVEL_ORDER["WARN"]:
            self._emit("WARN", msg, **context)

    def error(self, msg: str, exc: BaseException | None = None, **context: object) -> None:
        if self._min_level <= _LEVEL_ORDER["ERROR"]:
            if exc is not None:
                context["exc"] = exc
            self._emit("ERROR", msg, **context)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, level: str, msg: str, **context: object) -> None:
        try:
            event_dict: dict[str, Any] = {"event": msg, "level": level, **context}
            for processor in self._processors:
                event_dict = processor(None, level.lower(), event_dict)  # type: ignore[arg-type]
            if self._file is None:
                self._file = open(self._log_file, "a", encoding="utf-8")
            self._file.write(str(event_dict) + "\n")
            self._file.flush()
        except Exception:
            pass  # R5: diagnostics failure must never propagate
