# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""In-process job registry for detached background executions.

Each POST /jobs submission gets a unique job_id. The execution runs in a
background thread; callers poll GET /jobs/{id} or stream GET /jobs/{id}/stream.
The registry is in-process memory only — jobs are not persisted across restarts.
"""

from __future__ import annotations

import concurrent.futures
import secrets
import threading
from enum import Enum

from generic_ml_cache_core.application.domain.model.execution.ml_execution import MlExecution


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class Job:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.state = JobState.PENDING
        self.execution: MlExecution | None = None
        self.error: str | None = None
        self._done_event = threading.Event()

    def wait(self, timeout: float | None = None) -> bool:
        return self._done_event.wait(timeout=timeout)

    def mark_running(self) -> None:
        self.state = JobState.RUNNING

    def mark_done(self, execution: MlExecution) -> None:
        self.execution = execution
        self.state = JobState.DONE
        self._done_event.set()

    def mark_error(self, error: str) -> None:
        self.error = error
        self.state = JobState.ERROR
        self._done_event.set()


class JobRegistry:
    """Thread-safe in-memory registry of submitted jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="gmlc-job"
        )

    def submit(self, fn, *args) -> Job:
        job_id = secrets.token_hex(8)
        job = Job(job_id)
        with self._lock:
            self._jobs[job_id] = job

        def _run() -> None:
            job.mark_running()
            try:
                execution = fn(*args)
                job.mark_done(execution)
            except Exception as exc:  # noqa: BLE001 — in-process job boundary: any failure → job error
                job.mark_error(str(exc))

        self._executor.submit(_run)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_ids(self) -> list:
        with self._lock:
            return list(self._jobs.keys())
