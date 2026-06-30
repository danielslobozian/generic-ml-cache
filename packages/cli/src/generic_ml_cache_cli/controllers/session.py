# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: session sub-commands — start, update, clear-spec, report, tag."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from generic_ml_cache_core.application.domain.model.session.session_spec import SessionSpec
from generic_ml_cache_core.application.port.inbound.session_admin.clear_session_spec_command import (
    ClearSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_admin.set_session_spec_command import (
    SetSessionSpecCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.list_session_tags_command import (
    ListSessionTagsCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.tag_session_command import (
    TagSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_tags.untag_session_command import (
    UntagSessionCommand,
)
from generic_ml_cache_core.application.usecase.session_report import build_session_report

from generic_ml_cache_cli import config
from generic_ml_cache_cli._compose import build_use_cases
from generic_ml_cache_cli.composition import (
    _db_conn_factory,
    _make_diag,
    _store_root,
)
from generic_ml_cache_cli.presenters.session import (
    _render_session_report,
    _session_report_json,
)


def _parse_spec_args(args: argparse.Namespace) -> SessionSpec | None:
    """Return a SessionSpec from --client/--model/--effort, or None if all are absent.
    Raises ValueError on a partial spec (some but not all flags supplied).
    """
    client = getattr(args, "client", None)
    model = getattr(args, "model", None)
    effort = getattr(args, "effort", None)
    provided = [x is not None for x in (client, model, effort)]
    if not any(provided):
        return None
    if not all(provided):
        raise ValueError("--client, --model, and --effort must all be supplied together")
    return SessionSpec(client=str(client), model=str(model), effort=str(effort))


def _cmd_session_start(args: argparse.Namespace) -> int:
    import uuid

    session_id = str(uuid.uuid4())
    # Print only the id, so it is scriptable: SESSION=$(gmlcache session start)
    print(session_id)
    tags = getattr(args, "tag", None) or []
    try:
        spec = _parse_spec_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if tags or spec:
        settings = config.resolve_settings(config.load())
        store_root = Path(str(settings["store"][0]))
        wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))
        for tag in tags:
            wired.session_tags.tag(TagSessionCommand(session_id, tag))
        if spec is not None:
            wired.session_admin.set_spec(SetSessionSpecCommand(session_id, spec))
    return 0


def _cmd_session_update(args: argparse.Namespace) -> int:
    try:
        spec = _parse_spec_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if spec is None:
        print(
            "error: --client, --model, and --effort are all required for session update",
            file=sys.stderr,
        )
        return 2
    store_root = _store_root()
    if store_root is None:
        return 4
    wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))
    wired.session_admin.set_spec(SetSessionSpecCommand(args.session_id, spec))
    if not args.json:
        print(f"spec  : {spec.client}/{spec.model}/{spec.effort!r}")
    else:
        import json

        print(
            json.dumps(
                {
                    "session": args.session_id,
                    "spec": {
                        "client": spec.client,
                        "model": spec.model,
                        "effort": spec.effort,
                    },
                },
                indent=2,
            )
        )
    return 0


def _cmd_session_clear_spec(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))
    wired.session_admin.clear_spec(ClearSessionSpecCommand(args.session_id))
    if not args.json:
        print(f"spec cleared for session {args.session_id}")
    else:
        import json

        print(json.dumps({"session": args.session_id, "spec": None}, indent=2))
    return 0


def _cmd_session_report(args: argparse.Namespace) -> int:
    store_root = _store_root()
    if store_root is None:
        return 4
    session_id = getattr(args, "session_id", None)
    tag = getattr(args, "tag", None)
    if not session_id and not tag:
        print("gmlc: provide a session id or --tag <tag>", file=sys.stderr)
        return 1
    wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))

    if tag:
        return _cmd_session_report_by_tag(wired, tag, args.json)

    assert session_id is not None
    events = wired.metrics.session_events(str(session_id))
    tags = wired.metrics.session_tags(str(session_id))
    # Join each event's execution to its token usage (the current execution per key).
    usage_by_key = {}
    for key in {e.execution_key for e in events if e.execution_key}:
        execution = wired.repository.find_current(key)
        if execution is not None:
            usage_by_key[key] = execution.token_usage
    report = build_session_report(str(session_id), events, usage_by_key)

    if args.json:
        import json

        print(json.dumps(_session_report_json(report, tags), indent=2))
        return 0
    if report.invocations == 0 and not tags:
        print(f"no events recorded for session {session_id!r}")
        return 0
    print(_render_session_report(report, tags))
    return 0


def _cmd_session_report_by_tag(  # NOSONAR — always 0 by design
    wired, tag: str, as_json: bool
) -> int:
    session_ids = wired.metrics.session_ids_for_tag(tag)
    if not session_ids:
        print(f"no sessions tagged {tag!r}")
        return 0
    # Collect events from all matching sessions; build one merged report.
    all_events = []
    for session_id in session_ids:
        all_events.extend(wired.metrics.session_events(session_id))
    usage_by_key = {}
    for key in {e.execution_key for e in all_events if e.execution_key}:
        execution = wired.repository.find_current(key)
        if execution is not None:
            usage_by_key[key] = execution.token_usage
    report = build_session_report(tag, all_events, usage_by_key)

    if as_json:
        import json

        payload = _session_report_json(report, [tag])
        payload["tag"] = tag
        payload["session_count"] = len(session_ids)
        del payload["session"]
        print(json.dumps(payload, indent=2))
        return 0
    lines = [f"tag         : {tag}", f"sessions    : {len(session_ids)}"]
    print("\n".join(lines))
    print(_render_session_report(report))
    return 0  # NOSONAR — always 0: all paths are success (found or not-found)


def _cmd_session_tag(args: argparse.Namespace) -> int:
    if not args.add and not args.remove:
        print("error: supply at least one --add or --remove flag", file=sys.stderr)
        return 2
    store_root = _store_root()
    if store_root is None:
        return 4
    wired = build_use_cases(_db_conn_factory(store_root), store_root, diag=_make_diag(args))
    for tag in args.add:
        wired.session_tags.tag(TagSessionCommand(args.session_id, tag))
    for tag in args.remove:
        wired.session_tags.untag(UntagSessionCommand(args.session_id, tag))
    tags = wired.session_tags.list_tags(ListSessionTagsCommand(args.session_id))
    if not args.json:
        print(f"tags : {', '.join(sorted(tags))}")
    else:
        import json

        print(json.dumps({"session": args.session_id, "tags": tags}, indent=2))
    return 0


def _cmd_session(_args: argparse.Namespace) -> int:
    print(
        "usage: gmlcache session start | tag | update | clear-spec | report",
        file=sys.stderr,
    )
    return 2
