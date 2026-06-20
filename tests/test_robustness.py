# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Partial-record robustness (0.0.8): a crash, timeout, or interruption mid-record
never leaves a half-written cassette or a stray temp file, and a timeout surfaces
cleanly rather than as an uncaught error."""

from __future__ import annotations

import subprocess

import pytest

import generic_ml_cache.adapter.out.storage.store as store_mod
from generic_ml_cache import Mode, Request, cli, resolve
from generic_ml_cache.application.domain.model.cassette import Cassette, Response


def req(prompt: str) -> Request:
    return Request(client="fake", model="m1", effort="high", context="ctx", prompt=prompt)


def seeded_cassette() -> Cassette:
    return Cassette(
        client="fake",
        model="m1",
        effort="high",
        input_data={"context": "c", "prompt": "p"},
        response=Response(stdout="x"),
    )


# --- timeout ---------------------------------------------------------------


def test_timeout_kills_the_call_and_records_nothing(store):
    # The fake client sleeps far past the timeout, so the call can only end by
    # being killed; the timeout unwinds before any write, leaving the store clean.
    with pytest.raises(subprocess.TimeoutExpired):
        resolve(req("SLEEP 30"), store, mode=Mode.CACHE, timeout=0.5)
    assert len(store) == 0
    assert list(store.root.glob("*.tmp")) == []


def test_cli_maps_timeout_to_124(monkeypatch):
    def _raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="client", timeout=0.5)

    monkeypatch.setattr(cli, "resolve", _raise_timeout)
    code = cli.main(
        ["run", "--client", "fake", "--model", "m", "--prompt", "STDOUT hi", "--timeout", "0.5"]
    )
    assert code == 124


# --- store write atomicity -------------------------------------------------


def test_normal_save_leaves_only_the_json(store):
    store.save(seeded_cassette())
    assert len(list(store.root.glob("*.json"))) == 1
    assert list(store.root.glob("*.tmp")) == []


def test_serialization_failure_writes_nothing(store, monkeypatch):
    # If rendering the cassette raises, nothing on disk is touched.
    def _boom(_self):
        raise RuntimeError("serialize boom")

    monkeypatch.setattr(Cassette, "to_json", _boom)
    with pytest.raises(RuntimeError):
        store.save(seeded_cassette())
    assert list(store.root.glob("*.json")) == []
    assert list(store.root.glob("*.tmp")) == []


def test_replace_failure_cleans_up_the_temp(store, monkeypatch):
    # The temp file is written, then the atomic replace fails: the target must not
    # appear and the temp must be removed (no stray temp, no half-written cassette).
    def _boom(_src, _dst):
        raise OSError("replace failed")

    monkeypatch.setattr(store_mod.os, "replace", _boom)
    with pytest.raises(OSError):
        store.save(seeded_cassette())
    assert list(store.root.glob("*.json")) == []
    assert list(store.root.glob("*.tmp")) == []
