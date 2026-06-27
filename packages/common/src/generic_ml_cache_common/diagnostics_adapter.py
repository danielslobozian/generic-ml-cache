# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""StructlogDiagnosticsAdapter — file-backed, logback-style implementation.

Writes structured diagnostic lines to a rotating log file. Each line carries:
  timestamp  [thread-name:thread-id]  LEVEL  ClassName.method_name:lineno — msg  k=v …

Format is human-readable text (logback convention) by default; pass
``fmt="json"`` for newline-delimited JSON suitable for log aggregators.

Usage (composition root in CLI or daemon):

    from generic_ml_cache_common.diagnostics_adapter import StructlogDiagnosticsAdapter
    diag = StructlogDiagnosticsAdapter(log_file=store_root / "gmlcache.log", level="INFO")
    use_cases = build_use_cases(conn_factory, diag=diag, ...)
"""

from __future__ import annotations

import sys
import threading
import traceback
from enum import Enum
from pathlib import Path
from typing import IO, Any, Dict, Optional

import structlog
from structlog.types import EventDict, WrappedLogger

from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort

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
# Custom structlog processors
# ---------------------------------------------------------------------------


def _caller_info_processor(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
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
            event_dict["caller"] = (
                f"{cls}.{func}:{lineno}" if cls else f"{func}:{lineno}"
            )
            break
        frame = frame.f_back  # type: ignore[assignment]
    return event_dict


def _thread_info_processor(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    t = threading.current_thread()
    event_dict["thread"] = f"{t.name}:{threading.get_ident()}"
    return event_dict


def _exc_processor(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Render the ``exc`` key as a formatted traceback string."""
    exc: Optional[BaseException] = event_dict.pop("exc", None)
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

        extras = "  ".join(
            f"{k}={v}" for k, v in event_dict.items() if not k.startswith("_")
        )
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
        renderer = (
            _build_text_renderer() if fmt.lower() == "text" else _build_json_renderer()
        )
        self._processors = [
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f", utc=False),
            _thread_info_processor,
            _caller_info_processor,
            _exc_processor,
            structlog.processors.format_exc_info,
            renderer,
        ]
        self._log_file = log_file
        self._file: Optional[IO[str]] = None

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

    def error(
        self, msg: str, exc: Optional[BaseException] = None, **context: object
    ) -> None:
        if self._min_level <= _LEVEL_ORDER["ERROR"]:
            if exc is not None:
                context["exc"] = exc
            self._emit("ERROR", msg, **context)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, level: str, msg: str, **context: object) -> None:
        try:
            event_dict: Dict[str, Any] = {"event": msg, "level": level, **context}
            for processor in self._processors:
                event_dict = processor(None, level.lower(), event_dict)  # type: ignore[arg-type]
            if self._file is None:
                self._file = open(self._log_file, "a", encoding="utf-8")  # noqa: SIM115
            self._file.write(str(event_dict) + "\n")
            self._file.flush()
        except Exception:
            pass  # R5: diagnostics failure must never propagate
