# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""ExecutionOutput."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from generic_ml_cache.application.domain.model.captured_file import CapturedFile


@dataclass(frozen=True)
class ExecutionOutput:
    """The result of running an ML client: stdout, stderr, exit code, and any
    generated files captured from the isolated run folder.

    TokenUsage is NOT part of this object — it is accounting data, database-bound
    and mutable by append. It lives separately on MlExecution.
    """

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    files: List[CapturedFile] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "files": [captured_file.to_dict() for captured_file in self.files],
        }

    @classmethod
    def from_dict(cls, execution_output_dict: Dict[str, Any]) -> "ExecutionOutput":
        return cls(
            stdout=execution_output_dict.get("stdout", ""),
            stderr=execution_output_dict.get("stderr", ""),
            exit_code=int(execution_output_dict.get("exit_code", 0)),
            files=[
                CapturedFile.from_dict(captured_file_dict)
                for captured_file_dict in execution_output_dict.get("files", [])
            ],
        )
