# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for detached ("async") execution jobs (Slice 1: worker, lock, submit)."""

from __future__ import annotations

import argparse

from generic_ml_cache_cli import async_jobs
from generic_ml_cache_cli.async_jobs import (
    JobStore,
    derived_state,
    hold_job_lock,
    job_lock_held,
)
from generic_ml_cache_cli.cli import _cmd_worker, main


def _spec():
    return {
        "client": "fake",
        "model": "m1",
        "effort": "high",
        "context": "",
        "prompt": "STDOUT hi",
        "system_prompt": None,
        "input_file_paths": [],
        "allow_paths": [],
        "trust_scan": False,
        "client_args": [],
        "grants": [],
        "cache_mode": "cache",
        "persistence_depth": "cache",
        "record_on_error": False,
        "tags": [],
        "session_id": None,
        "executable": None,
        "timeout": None,
    }


# --- the worker (run in-process; no real detach) -----------------------------


def test_worker_runs_the_job_and_records_success(tmp_path):
    store = JobStore(tmp_path)
    store.write_spec("j1", _spec())
    rc = _cmd_worker(argparse.Namespace(store_root=str(tmp_path), job_id="j1"))
    assert rc == 0
    status = store.read_status("j1")
    assert status["state"] == "succeeded"
    assert status["execution_key"]  # the result was recorded into the cache
    assert "started_at" in status and "ended_at" in status
    # the worker holds the lock only while running; it is free once done
    assert not job_lock_held(store.lock_path("j1"))


def test_worker_records_failure_on_a_bad_client(tmp_path):
    spec = _spec()
    spec["client"] = "does-not-exist"
    store = JobStore(tmp_path)
    store.write_spec("j2", spec)
    rc = _cmd_worker(argparse.Namespace(store_root=str(tmp_path), job_id="j2"))
    assert rc == 1
    status = store.read_status("j2")
    assert status["state"] == "failed" and status["error"]


# --- the liveness lock + derived state ---------------------------------------


def test_job_lock_probe_reflects_holding(tmp_path):
    lock = tmp_path / "j.lock"
    assert not job_lock_held(lock)  # nothing holds it (and the file may not exist)
    with hold_job_lock(lock):
        assert job_lock_held(lock)  # a holder is detected
    assert not job_lock_held(lock)  # released


def test_derived_state_flags_a_vanished_worker_as_interrupted():
    assert derived_state({"state": "running"}, lock_held=True) == "running"
    assert derived_state({"state": "running"}, lock_held=False) == "interrupted"
    assert derived_state({"state": "succeeded"}, lock_held=False) == "succeeded"
    assert derived_state(None, lock_held=False) == "unknown"


# --- run --detach (spawn mocked) ---------------------------------------------


def test_run_detach_submits_a_job_and_prints_the_id(capsys, monkeypatch):
    spawned = []
    monkeypatch.setattr(async_jobs, "spawn_worker", lambda root, jid: spawned.append((root, jid)))
    rc = main(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--prompt",
            "STDOUT hi",
            "--detach",
        ]
    )
    assert rc == 0
    job_id = capsys.readouterr().out.strip()
    assert len(job_id) == 16 and job_id.isalnum()  # a hex id, printed alone (scriptable)
    assert len(spawned) == 1 and spawned[0][1] == job_id  # the worker was spawned for it
    store = JobStore(spawned[0][0])
    status = store.read_status(job_id)
    assert status["state"] == "submitted" and status["client"] == "fake"
    assert store.read_spec(job_id)["prompt"] == "STDOUT hi"
