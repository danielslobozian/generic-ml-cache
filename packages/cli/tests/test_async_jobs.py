# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Tests for detached ("async") execution jobs (Slice 1: worker, lock, submit)."""

from __future__ import annotations

import argparse

import pytest

from generic_ml_cache_cli import async_jobs
from generic_ml_cache_cli.async_jobs import (
    JobStore,
    derived_state,
    hold_job_lock,
    job_lock_held,
)
from generic_ml_cache_cli.cli import _cmd_worker, main

_RUN_BASE = ["run", "--client", "fake", "--model", "m1", "--effort", "high"]


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
    monkeypatch.setattr(
        async_jobs, "spawn_worker", lambda root, jid, token=None: spawned.append((root, jid))
    )
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


# --- execution status / result / list (Slice 2) ------------------------------


def _submit_via_run(monkeypatch, prompt="STDOUT hi"):
    captured = {}
    monkeypatch.setattr(
        async_jobs,
        "spawn_worker",
        lambda root, jid, token=None: captured.update(root=root, jid=jid),
    )
    main(
        [
            "run",
            "--client",
            "fake",
            "--model",
            "m1",
            "--effort",
            "high",
            "--prompt",
            prompt,
            "--detach",
        ]
    )
    return captured["jid"], captured["root"]


def _submit_and_run(monkeypatch, prompt="STDOUT hi"):
    jid, root = _submit_via_run(monkeypatch, prompt)
    _cmd_worker(argparse.Namespace(store_root=str(root), job_id=jid))
    return jid, root


def test_execution_status_and_result_for_a_succeeded_job(capsys, monkeypatch):
    jid, _ = _submit_and_run(monkeypatch)
    capsys.readouterr()
    assert main(["execution", "status", jid]) == 0
    out = capsys.readouterr().out
    assert "state      : succeeded" in out and "result     :" in out
    assert main(["execution", "result", jid]) == 0
    assert "hi" in capsys.readouterr().out


def test_execution_status_json(capsys, monkeypatch):
    import json

    jid, _ = _submit_and_run(monkeypatch)
    capsys.readouterr()
    assert main(["execution", "status", jid, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["state"] == "succeeded" and data["execution_key"]


def test_interrupted_when_running_but_no_worker_holds_the_lock(capsys, monkeypatch):
    jid, root = _submit_via_run(monkeypatch)
    # a worker that set running then vanished: status says running, nothing holds the lock
    async_jobs.JobStore(root).update_status(jid, state="running", started_at=async_jobs.now())
    capsys.readouterr()
    assert main(["execution", "status", jid]) == 0
    assert "state      : interrupted" in capsys.readouterr().out
    assert main(["execution", "result", jid]) == 1  # interrupted is not a result


def test_result_on_a_live_running_job_is_not_ready(monkeypatch):
    jid, root = _submit_via_run(monkeypatch)
    store = async_jobs.JobStore(root)
    store.update_status(jid, state="running")
    with async_jobs.hold_job_lock(store.lock_path(jid)):  # a live worker holds the lock
        assert main(["execution", "result", jid]) == 75  # EX_TEMPFAIL: try again later


def test_execution_list_unknown_and_usage(capsys, monkeypatch):
    jid, _ = _submit_and_run(monkeypatch)
    capsys.readouterr()
    assert main(["execution", "list"]) == 0
    out = capsys.readouterr().out
    assert jid in out and "succeeded" in out
    assert main(["execution", "status", "nope"]) == 4  # unknown job
    capsys.readouterr()
    assert main(["execution"]) == 2  # bare -> usage
    assert "execution status" in capsys.readouterr().err


# --- watch + materialize (Slice 3) -------------------------------------------


def _write_directive(relpath, content):
    import base64

    return f"WRITE {relpath} {base64.b64encode(content.encode()).decode()}"


def test_execution_watch_replays_a_finished_job(capsys, monkeypatch):
    jid, _ = _submit_and_run(monkeypatch)
    capsys.readouterr()
    assert main(["execution", "watch", jid]) == 0
    out = capsys.readouterr().out
    assert "submitted" in out and "running" in out and "succeeded" in out


def test_execution_watch_reports_interrupted(capsys, monkeypatch):
    jid, root = _submit_via_run(monkeypatch)
    async_jobs.JobStore(root).update_status(jid, state="running", started_at=async_jobs.now())
    capsys.readouterr()
    assert main(["execution", "watch", jid]) == 1
    assert "interrupted" in capsys.readouterr().err


def test_execution_materialize_writes_generated_files(tmp_path, capsys, monkeypatch):
    jid, _ = _submit_and_run(monkeypatch, prompt=_write_directive("out.txt", "hello-async"))
    capsys.readouterr()
    outdir = tmp_path / "materialized"
    assert main(["execution", "materialize", jid, "--output-dir", str(outdir)]) == 0
    assert (outdir / "out.txt").read_text() == "hello-async"


def test_materialize_refuses_an_unfinished_job(tmp_path, monkeypatch):
    jid, root = _submit_via_run(monkeypatch)
    store = async_jobs.JobStore(root)
    store.update_status(jid, state="running")
    with async_jobs.hold_job_lock(store.lock_path(jid)):  # a live running job
        rc = main(["execution", "materialize", jid, "--output-dir", str(tmp_path / "out")])
    assert rc == 4  # not succeeded -> nothing to materialize


# --- detach is refused on an encrypted store (the gate is the state, not the token) --


def _encrypt_and_get_token(capsys):
    assert main(["encrypt"]) == 0  # encrypt the (empty) isolated store
    out = capsys.readouterr().out
    tokens = [w for w in out.split() if len(w) == 64 and all(c in "0123456789abcdef" for c in w)]
    assert tokens, "encrypt should print a hex token"
    return tokens[0]


def test_detach_without_a_token_is_refused_on_an_encrypted_store(capsys, monkeypatch):
    pytest.importorskip("cryptography")
    spawned = []
    monkeypatch.setattr(async_jobs, "spawn_worker", lambda *a, **k: spawned.append(a))
    _encrypt_and_get_token(capsys)
    rc = main(_RUN_BASE + ["--prompt", "STDOUT hi", "--detach"])
    assert rc == 4
    assert "encrypted" in capsys.readouterr().err
    assert spawned == []  # refused upfront: no worker, nothing written


def test_detached_run_round_trips_on_an_encrypted_store(capsys, monkeypatch):
    pytest.importorskip("cryptography")
    token = _encrypt_and_get_token(capsys)
    captured = {}
    monkeypatch.setattr(
        async_jobs,
        "spawn_worker",
        lambda root, jid, token=None: captured.update(root=root, jid=jid, token=token),
    )
    # submit with the token; it is handed to the worker (via env in real life), never to disk
    assert main(_RUN_BASE + ["--prompt", "STDOUT secret-hi", "--detach", "--token", token]) == 0
    capsys.readouterr()
    assert captured["token"] == token
    assert "token" not in async_jobs.JobStore(captured["root"]).read_spec(captured["jid"])

    # run the worker with the token in its environment, as the spawner would have set it
    monkeypatch.setenv("GMLCACHE_TOKEN", token)
    assert (
        _cmd_worker(argparse.Namespace(store_root=str(captured["root"]), job_id=captured["jid"]))
        == 0
    )
    monkeypatch.delenv("GMLCACHE_TOKEN", raising=False)

    # readable with the token; refused without it (the blob is genuinely encrypted)
    capsys.readouterr()
    assert main(["execution", "result", captured["jid"], "--token", token]) == 0
    assert "secret-hi" in capsys.readouterr().out
    assert main(["execution", "result", captured["jid"]]) == 4
