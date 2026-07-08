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
from generic_ml_cache_core.application.port.inbound.session_report.report_for_session_command import (
    ReportForSessionCommand,
)
from generic_ml_cache_core.application.port.inbound.session_report.report_for_tag_command import (
    ReportForTagCommand,
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
from generic_ml_cache_core.application.wiring.application_api import ApplicationApi

from generic_ml_cache_cli import config
from generic_ml_cache_cli._compose import build_use_cases
from generic_ml_cache_cli.composition import (
    make_diag,
    store_root,
)
from generic_ml_cache_cli.presenters.session import (
    render_session_report,
    session_report_json,
)


def _parse_spec_args(args: argparse.Namespace) -> SessionSpec | None:
    """Return a SessionSpec from --client/--model, or None if neither is given.

    A spec needs ``--client`` and ``--model`` together; ``--effort`` is optional and
    defaults to empty (the client's own default, or a model-encoded effort like Cursor's).
    Raises ValueError on a partial spec: only one of client/model, or effort with neither.
    """
    client = getattr(args, "client", None)
    model = getattr(args, "model", None)
    effort = getattr(args, "effort", None)
    if client is None and model is None:
        if effort is not None:
            raise ValueError("--effort requires --client and --model")
        return None
    if client is None or model is None:
        raise ValueError("--client and --model must be supplied together")
    return SessionSpec(client=str(client), model=str(model), effort=str(effort or ""))


def cmd_session_start(args: argparse.Namespace) -> int:
    import uuid

    session_id = str(uuid.uuid4())
    # Print only the id, so it is scriptable: SESSION=$(gmlcache session start)
    print(session_id)
    tags: list[str] = getattr(args, "tag", None) or []
    try:
        spec = _parse_spec_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if tags or spec:
        settings = config.resolve_settings(config.load())
        store_root_path = Path(str(settings["store"][0]))
        wired = build_use_cases(store_root_path, diag=make_diag(args))
        for tag in tags:
            wired.tag_session.tag(TagSessionCommand(session_id, tag))
        if spec is not None:
            wired.set_session_spec.set_spec(SetSessionSpecCommand(session_id, spec))
    return 0


def cmd_session_update(args: argparse.Namespace) -> int:
    try:
        spec = _parse_spec_args(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if spec is None:
        print(
            "error: --client and --model are required for session update",
            file=sys.stderr,
        )
        return 2
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    wired = build_use_cases(store_root_path, diag=make_diag(args))
    wired.set_session_spec.set_spec(SetSessionSpecCommand(args.session_id, spec))
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


def cmd_session_clear_spec(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    wired = build_use_cases(store_root_path, diag=make_diag(args))
    wired.clear_session_spec.clear_spec(ClearSessionSpecCommand(args.session_id))
    if not args.json:
        print(f"spec cleared for session {args.session_id}")
    else:
        import json

        print(json.dumps({"session": args.session_id, "spec": None}, indent=2))
    return 0


def cmd_session_report(args: argparse.Namespace) -> int:
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    session_id = getattr(args, "session_id", None)
    tag = getattr(args, "tag", None)
    if not session_id and not tag:
        print("gmlc: provide a session id or --tag <tag>", file=sys.stderr)
        return 1
    wired = build_use_cases(store_root_path, diag=make_diag(args))

    if tag:
        return _cmd_session_report_by_tag(wired, tag, args.json)

    assert session_id is not None
    report = wired.report_for_session.report_for_session(ReportForSessionCommand(str(session_id)))
    tags = wired.list_session_tags.list_tags(ListSessionTagsCommand(str(session_id)))

    if args.json:
        import json

        print(json.dumps(session_report_json(report, tags), indent=2))
        return 0
    if report.invocations == 0 and not tags:
        print(f"no events recorded for session {session_id!r}")
        return 0
    print(render_session_report(report, tags))
    return 0


def _cmd_session_report_by_tag(  # NOSONAR — always 0 by design
    wired: ApplicationApi,
    tag: str,
    as_json: bool,
) -> int:
    result = wired.report_for_tag.report_for_tag(ReportForTagCommand(tag))
    if result.session_count == 0:
        print(f"no sessions tagged {tag!r}")
        return 0
    report = result.report

    if as_json:
        import json

        payload = session_report_json(report, [tag])
        payload["tag"] = tag
        payload["session_count"] = result.session_count
        del payload["session"]
        print(json.dumps(payload, indent=2))
        return 0
    lines = [f"tag         : {tag}", f"sessions    : {result.session_count}"]
    print("\n".join(lines))
    print(render_session_report(report))
    return 0  # NOSONAR — always 0: all paths are success (found or not-found)


def cmd_session_tag(args: argparse.Namespace) -> int:
    if not args.add and not args.remove:
        print("error: supply at least one --add or --remove flag", file=sys.stderr)
        return 2
    store_root_path = store_root()
    if store_root_path is None:
        return 4
    wired = build_use_cases(store_root_path, diag=make_diag(args))
    for tag in args.add:
        wired.tag_session.tag(TagSessionCommand(args.session_id, tag))
    for tag in args.remove:
        wired.untag_session.untag(UntagSessionCommand(args.session_id, tag))
    tags = wired.list_session_tags.list_tags(ListSessionTagsCommand(args.session_id))
    if not args.json:
        print(f"tags : {', '.join(sorted(tags))}")
    else:
        import json

        print(json.dumps({"session": args.session_id, "tags": tags}, indent=2))
    return 0


def cmd_session(_args: argparse.Namespace) -> int:
    print(
        "usage: gmlcache session start | tag | update | clear-spec | report",
        file=sys.stderr,
    )
    return 2
