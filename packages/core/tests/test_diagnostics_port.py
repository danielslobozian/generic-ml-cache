"""Tests for DiagnosticsPort contract and NullDiagnosticsAdapter."""

from __future__ import annotations

from generic_ml_cache_core.application.port.out.null_diagnostics_adapter import (
    NullDiagnosticsAdapter,
)
from generic_ml_cache_core.application.port.out.diagnostics_port import DiagnosticsPort


def test_null_adapter_is_diagnostics_port() -> None:
    assert isinstance(NullDiagnosticsAdapter(), DiagnosticsPort)


def test_null_adapter_debug_does_not_raise() -> None:
    NullDiagnosticsAdapter().debug("test", key="val")


def test_null_adapter_info_does_not_raise() -> None:
    NullDiagnosticsAdapter().info("test", key="val")


def test_null_adapter_warn_does_not_raise() -> None:
    NullDiagnosticsAdapter().warn("test", key="val")


def test_null_adapter_error_does_not_raise() -> None:
    NullDiagnosticsAdapter().error("test")


def test_null_adapter_error_with_exception_does_not_raise() -> None:
    NullDiagnosticsAdapter().error("test", exc=ValueError("boom"), key="val")


def test_null_adapter_swallows_all_levels_silently(capsys) -> None:
    diag = NullDiagnosticsAdapter()
    diag.debug("d")
    diag.info("i")
    diag.warn("w")
    diag.error("e", exc=RuntimeError("x"))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
