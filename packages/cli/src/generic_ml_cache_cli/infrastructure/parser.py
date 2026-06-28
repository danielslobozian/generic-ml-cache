# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Argument parser for the gmlcache CLI."""

from __future__ import annotations

import argparse

from generic_ml_cache_core.adapter.registry import registered_local_names, registered_names
from generic_ml_cache_core.application.domain.model.run.cache_mode import CacheMode
from generic_ml_cache_core.application.domain.model.run.persistence_depth import PersistenceDepth

from generic_ml_cache_cli import __version__
from generic_ml_cache_cli.controllers.daemon import (
    _cmd_daemon,
    _cmd_daemon_start,
    _cmd_daemon_status,
    _cmd_daemon_stop,
    _cmd_status_line,
)
from generic_ml_cache_cli.controllers.encrypt import (
    _cmd_decrypt,
    _cmd_encrypt,
    _cmd_invalidate,
    _cmd_rotate,
)
from generic_ml_cache_cli.controllers.execution import (
    _cmd_execution,
    _cmd_execution_list,
    _cmd_execution_materialize,
    _cmd_execution_result,
    _cmd_execution_status,
    _cmd_execution_watch,
    _cmd_worker,
)
from generic_ml_cache_cli.controllers.run import (
    GRANT_CHOICES,
    _GRANT_HELP,
    _cmd_alias,
    _cmd_run,
)
from generic_ml_cache_cli.controllers.session import (
    _cmd_session,
    _cmd_session_clear_spec,
    _cmd_session_report,
    _cmd_session_start,
    _cmd_session_tag,
    _cmd_session_update,
)
from generic_ml_cache_cli.controllers.config import (
    _cmd_config,
    _cmd_config_show,
    _cmd_config_validate,
)
from generic_ml_cache_cli.controllers.setup import (
    _cmd_doctor,
    _cmd_init,
    _cmd_models,
    _cmd_status,
)
from generic_ml_cache_cli.controllers.store import (
    _cmd_check,
    _cmd_export,
    _cmd_inspect,
    _cmd_list,
    _cmd_purge,
    _cmd_stats,
    _cmd_tags,
)
from generic_ml_cache_cli.presenters.shared import _use_color, render_banner

_JSON_HELP = "emit machine-readable JSON"
_TOKEN_HELP = "encryption token if the store is encrypted (or set GMLCACHE_TOKEN)"
_JOB_ID_HELP = "the execution id"


class _BannerParser(argparse.ArgumentParser):
    """An ArgumentParser whose full help is fronted by the banner, so the banner
    shows on ``-h`` and on a bare invocation (but not on terse usage/error lines)."""

    def format_help(self) -> str:
        return render_banner(_use_color()) + "\n\n" + super().format_help()


def _add_shared_run_options(parser: argparse.ArgumentParser) -> None:
    """Add the run-resolution options shared by `run` and `alias` (mode, persistence,
    record policy, the executable seam, encryption token, session, timeout). Both
    commands resolve a cached call the same way, so they share this surface verbatim."""
    parser.add_argument(
        "--mode",
        choices=[m.value for m in CacheMode],
        default=None,
        help="resolution mode (default: cache, or config/env)",
    )
    parser.add_argument(
        "--persist",
        choices=[d.value for d in PersistenceDepth],
        default=None,
        help=(
            "how much to keep: meter (usage only, never replays), cache (+output, "
            "the default), or dataset (+input) (default: cache, or config/env)"
        ),
    )
    parser.add_argument("--offline", action="store_true", help="shortcut for --mode offline")
    parser.add_argument("--force", action="store_true", help="shortcut for --mode refresh")
    parser.add_argument(
        "--record-on-error",
        action="store_true",
        help="also cache a call that fails (non-zero exit); default is to store only successes",
    )
    parser.add_argument("--executable", help="override the client executable (the seam)")
    parser.add_argument(
        "--token", help="encryption token for an encrypted store (or set GMLCACHE_TOKEN)"
    )
    parser.add_argument(
        "--session", help="group this run under a session id (or set GMLCACHE_SESSION)"
    )
    parser.add_argument(
        "--timeout", type=float, default=None, help="seconds before the real call is killed"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _BannerParser(
        prog="gmlcache",
        description="Content-addressed cache/proxy for agentic CLI calls.",
    )
    parser.add_argument("--version", action="version", version=f"gmlcache {__version__}")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        default=None,
        dest="log_level",
        help="enable technical diagnostic logging at the given level (default: off)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        dest="log_file",
        metavar="PATH",
        help=(
            "write diagnostic logs to this file "
            "(default: <store>/gmlcache.log when --log-level is set)"
        ),
    )
    # metavar curates the usage/positional display (and hides internal commands like
    # __worker, which argparse's help=SUPPRESS does not reliably hide for subparsers).
    sub = parser.add_subparsers(dest="command", required=False, metavar="<command>")

    run = sub.add_parser("run", help="resolve a request (record on miss, replay on hit)")
    run.add_argument("--client", required=True, choices=registered_names())
    run.add_argument("--model", required=True)
    run.add_argument(
        "--effort",
        default="",
        help=(
            "reasoning effort (optional); omit to use the client's own default. "
            "For Cursor, leave this off when the model id already encodes effort."
        ),
    )
    run.add_argument("--prompt")
    run.add_argument("--prompt-file")
    run.add_argument("--context")
    run.add_argument("--context-file")
    run.add_argument("--system-prompt")
    run.add_argument("--system-prompt-file")
    run.add_argument(
        "--input-file",
        action="append",
        dest="input_file",
        metavar="PATH",
        help=(
            "a specific file the client will read in place; its content is "
            "fingerprinted into the cache key and the client is granted read "
            "access to it. Repeatable, any file type. The key watches content, "
            "not the name."
        ),
    )
    run.add_argument(
        "--allow-path",
        action="append",
        dest="allow_path",
        metavar="PATH",
        help=(
            "a folder the client may scan/read whose contents the cache cannot "
            "fingerprint. Declaring any allow-path makes the call run fresh and "
            "store nothing (non-cacheable). The client is granted read access to "
            "it via the prime directive (and --add-dir on Claude). Repeatable."
        ),
    )
    run.add_argument(
        "--client-arg",
        action="append",
        dest="client_arg",
        metavar="ARG",
        help=(
            "an extra argument appended verbatim to the client launch -- an escape "
            "hatch for client features the cache does not model. Part of the key "
            "(different args = different execution); only its fingerprint is stored, "
            "never the raw value. Repeatable; order is significant. Pass a "
            "dash-leading value with the =form: --client-arg=--flag."
        ),
    )
    run.add_argument(
        "--grant",
        action="append",
        dest="grant",
        choices=GRANT_CHOICES,
        help=_GRANT_HELP,
    )
    run.add_argument(
        "--tag",
        action="append",
        dest="tag",
        metavar="TAG",
        help=(
            "label this execution with a tag for later grouping/queries (repeatable; "
            "metadata only -- never part of the cache key). A relabel on a hit accumulates."
        ),
    )
    run.add_argument(
        "--json",
        action="store_true",
        help=(
            "emit a machine-readable JSON envelope (status, exit, files, normalized "
            "usage, stdout) instead of the raw answer -- for a parent process such "
            "as the workflow engine reading usage. Files are still written to the cwd."
        ),
    )
    _add_shared_run_options(run)
    run.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print cache diagnostics to stderr (breaks exact fidelity)",
    )
    run.add_argument(
        "--stream",
        nargs="?",
        const="./gmlc-stream.jsonl",
        default=None,
        metavar="PATH",
        help=(
            "write a live NDJSON progress stream as the call runs (run.start, the client's "
            "thinking/tool events, run.end) -- display-only, never changes what is recorded. "
            "Give a path, or pass --stream alone to write ./gmlc-stream.jsonl"
        ),
    )
    run.add_argument(
        "--detach",
        action="store_true",
        help=(
            "submit the run as a detached background job: print an execution id and return "
            "immediately; the work continues, queryable with `gmlcache execution ...`"
        ),
    )
    run.set_defaults(func=_cmd_run)

    aliasp = sub.add_parser(
        "alias",
        help=(
            "thin native-client wrapper: cache a raw native invocation -- everything "
            "after the client is passed to it verbatim and is the cache identity"
        ),
        description=(
            "Run a client through the cache as a thin wrapper. gmlcache's own options "
            "(below) come BEFORE the client; everything after the client is forwarded to "
            "it verbatim and keyed (by fingerprint) as the cache identity. No options are "
            "modelled or auto-completed. A replay reproduces the native call's stdout, "
            "stderr and exit; generated files are written by the live call only (no capture). "
            "Drop-in: alias claude='gmlcache alias claude'."
        ),
    )
    _add_shared_run_options(aliasp)
    aliasp.add_argument(
        "client", choices=registered_local_names(), help="the native client to wrap"
    )
    aliasp.add_argument(
        "native_args",
        nargs=argparse.REMAINDER,
        metavar="-- NATIVE_ARGS",
        help="the native client arguments, forwarded verbatim (this is the cache identity)",
    )
    aliasp.set_defaults(func=_cmd_alias)

    # Internal: no help= so it never appears as a help row; metavar hides it from the list.
    worker = sub.add_parser("__worker")
    worker.add_argument("store_root")
    worker.add_argument("job_id")
    worker.set_defaults(func=_cmd_worker)

    inspect = sub.add_parser("inspect", help="show a stored execution by its (short) key")
    inspect.add_argument("execution", help="an execution key, or a short prefix as shown by `list`")
    inspect.set_defaults(func=_cmd_inspect)

    check = sub.add_parser(
        "check",
        help="probe whether a call is already cached (read-only; launches and records nothing)",
    )
    check.add_argument("--client", required=True, choices=registered_local_names())
    check.add_argument("--model", required=True)
    check.add_argument(
        "--effort",
        default="",
        help="reasoning effort (optional); must match the run you would make",
    )
    check.add_argument("--prompt")
    check.add_argument("--prompt-file")
    check.add_argument("--context")
    check.add_argument("--context-file")
    check.add_argument(
        "--input-file",
        action="append",
        dest="input_file",
        metavar="PATH",
        help="an input file whose content is fingerprinted into the key (repeatable)",
    )
    check.add_argument(
        "--allow-path",
        action="append",
        dest="allow_path",
        metavar="PATH",
        help="a scan folder; declaring any makes the call non-cacheable (repeatable)",
    )
    check.add_argument(
        "--client-arg",
        action="append",
        dest="client_arg",
        metavar="ARG",
        help="extra arg keyed into the call, to probe a passthrough launch (repeatable)",
    )
    check.add_argument(
        "--grant",
        action="append",
        dest="grant",
        choices=GRANT_CHOICES,
        help="open a capability (net/read/write/shell/web-search), keyed into the call, to probe a granted launch (repeatable)",
    )
    check.add_argument("--json", action="store_true", help=_JSON_HELP)
    check.set_defaults(func=_cmd_check)

    doctor = sub.add_parser(
        "doctor",
        help="report which configured clients are present + their versions (advisory)",
    )
    doctor.add_argument(
        "--timeout", type=float, default=10.0, help="seconds before a version check is killed"
    )
    doctor.add_argument(
        "--host", default="127.0.0.1", metavar="HOST", help="daemon host for reachability check"
    )
    doctor.add_argument(
        "--port", type=int, default=8765, metavar="PORT", help="daemon port for reachability check"
    )
    _doctor_output = doctor.add_mutually_exclusive_group()
    _doctor_output.add_argument("--json", action="store_true", help=_JSON_HELP)
    _doctor_output.add_argument(
        "--bundle",
        action="store_true",
        help="write full diagnostic to a timestamped file (sensitive values redacted)",
    )
    doctor.set_defaults(func=_cmd_doctor)

    models = sub.add_parser(
        "models",
        help="list the models a client reports it can use (advisory; relayed from the client)",
    )
    models.add_argument(
        "client",
        nargs="?",
        help="client or API provider name (e.g. claude, gemini); omit to query every registered client",
    )
    models.add_argument("--executable", help="override the client executable (the seam)")
    models.add_argument(
        "--timeout", type=float, default=30.0, help="seconds before the listing call is killed"
    )
    models.add_argument("--json", action="store_true", help=_JSON_HELP)
    models.set_defaults(func=_cmd_models)

    status = sub.add_parser(
        "status",
        help="show the resolved configuration (which file loaded, effective settings)",
    )
    status.add_argument("--json", action="store_true", help=_JSON_HELP)
    status.set_defaults(func=_cmd_status)

    stats = sub.add_parser(
        "stats",
        help="show how many executions are stored, their total size split by client/model, "
        "and access counts",
    )
    stats.add_argument("--json", action="store_true", help=_JSON_HELP)
    stats.set_defaults(func=_cmd_stats)

    purgep = sub.add_parser(
        "purge",
        help="free stored blobs (soft purge) or erase all records (--hard)",
    )
    purgep.add_argument("key", nargs="?", help="execution key to purge")
    purgep.add_argument("--tag", help="purge all executions carrying this tag")
    purgep.add_argument("--session", help="purge all executions from this session")
    purgep.add_argument(
        "--session-tag",
        dest="session_tag",
        help="purge all executions from sessions carrying this tag",
    )
    purgep.add_argument("--all", action="store_true", help="purge every execution in the store")
    purgep.add_argument(
        "--hard",
        action="store_true",
        help="hard-delete: also remove DB records and access history "
        "(default: soft purge keeps statistics)",
    )
    purgep.add_argument(
        "--confirm",
        help='confirmation phrase required for --all (soft: "purge all"; hard: "hard delete all")',
    )
    purgep.add_argument("--json", action="store_true", help=_JSON_HELP)
    purgep.set_defaults(func=_cmd_purge)

    listp = sub.add_parser(
        "list", help="list stored executions, grouped by client/model (read-only)"
    )
    listp.add_argument("--client", help="only executions recorded for this client")
    listp.add_argument("--model", help="only executions recorded for this model")
    listp.add_argument(
        "--tag",
        action="append",
        dest="tag",
        metavar="TAG",
        help="only executions carrying any of these tags (repeatable; match-any)",
    )
    listp.add_argument(
        "--exclude-tag",
        action="append",
        dest="exclude_tag",
        metavar="TAG",
        help="drop executions carrying any of these tags (repeatable; match-any)",
    )
    listp.add_argument(
        "--session-tag",
        action="append",
        dest="session_tag",
        metavar="TAG",
        help="only executions from sessions carrying this tag (repeatable; match-any)",
    )
    listp.add_argument("--json", action="store_true", help=_JSON_HELP)
    listp.set_defaults(func=_cmd_list)

    tagsp = sub.add_parser(
        "tags",
        help="list the distinct tags in use across current executions, with counts (read-only)",
    )
    tagsp.add_argument("--json", action="store_true", help=_JSON_HELP)
    tagsp.set_defaults(func=_cmd_tags)

    exportp = sub.add_parser(
        "export",
        help="export the (input, output) dataset corpus as JSONL (read-only). Only entries "
        "stored at --persist dataset carry an input; others are skipped.",
    )
    exportp.add_argument(
        "--tag",
        action="append",
        dest="tag",
        metavar="TAG",
        help="only entries carrying any of these tags (repeatable; match-any)",
    )
    exportp.add_argument(
        "--exclude-tag",
        action="append",
        dest="exclude_tag",
        metavar="TAG",
        help="drop entries carrying any of these tags (repeatable; match-any)",
    )
    exportp.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write JSONL to FILE instead of stdout (a per-record summary still goes to stderr)",
    )
    exportp.add_argument("--token", help=_TOKEN_HELP)
    exportp.set_defaults(func=_cmd_export)

    encryptp = sub.add_parser(
        "encrypt", help="enable at-rest encryption of the store (generates and shows a token)"
    )
    encryptp.set_defaults(func=_cmd_encrypt)

    decryptp = sub.add_parser(
        "decrypt", help="disable encryption (decrypts the store back to plaintext; needs the token)"
    )
    decryptp.add_argument("--token", help="the encryption token (or set GMLCACHE_TOKEN)")
    decryptp.set_defaults(func=_cmd_decrypt)

    rotatep = sub.add_parser(
        "rotate", help="rotate the encryption token (needs the current token; shows the new one)"
    )
    rotatep.add_argument("--token", help="the current encryption token (or set GMLCACHE_TOKEN)")
    rotatep.set_defaults(func=_cmd_rotate)

    invalidatep = sub.add_parser(
        "invalidate",
        help="wipe the cache (crypto-shred) — the escape when the token is lost. Needs --yes.",
    )
    invalidatep.add_argument("--yes", action="store_true", help="confirm the irreversible wipe")
    invalidatep.set_defaults(func=_cmd_invalidate)

    session = sub.add_parser("session", help="group a workflow's runs under a session id")
    session_sub = session.add_subparsers(dest="session_command")
    session_start = session_sub.add_parser("start", help="generate a new session id and print it")
    session_start.add_argument(
        "--tag",
        action="append",
        metavar="TAG",
        help="attach a tag to the session (repeatable)",
    )
    session_start.add_argument("--client", metavar="CLIENT", help="adapter for the session spec")
    session_start.add_argument("--model", metavar="MODEL", help="model for the session spec")
    session_start.add_argument(
        "--effort",
        metavar="EFFORT",
        help="effort for the session spec (empty string for Cursor)",
    )
    session_start.set_defaults(func=_cmd_session_start)
    session_update = session_sub.add_parser(
        "update", help="replace the execution spec on an existing session"
    )
    session_update.add_argument("session_id", help="the session id to update")
    session_update.add_argument(
        "--client", required=True, metavar="CLIENT", help="adapter for the new spec"
    )
    session_update.add_argument(
        "--model", required=True, metavar="MODEL", help="model for the new spec"
    )
    session_update.add_argument(
        "--effort",
        required=True,
        metavar="EFFORT",
        help="effort for the new spec (empty string for Cursor)",
    )
    session_update.add_argument("--json", action="store_true", help=_JSON_HELP)
    session_update.set_defaults(func=_cmd_session_update)
    session_clear_spec = session_sub.add_parser(
        "clear-spec", help="remove the execution spec from an existing session"
    )
    session_clear_spec.add_argument("session_id", help="the session id to clear the spec from")
    session_clear_spec.add_argument("--json", action="store_true", help=_JSON_HELP)
    session_clear_spec.set_defaults(func=_cmd_session_clear_spec)
    session_tag_cmd = session_sub.add_parser(
        "tag", help="add or remove tags on an existing session"
    )
    session_tag_cmd.add_argument("session_id", help="the session id to tag")
    session_tag_cmd.add_argument(
        "--add",
        action="append",
        default=[],
        metavar="TAG",
        help="tag to attach (repeatable)",
    )
    session_tag_cmd.add_argument(
        "--remove",
        action="append",
        default=[],
        metavar="TAG",
        help="tag to detach (repeatable)",
    )
    session_tag_cmd.add_argument("--json", action="store_true", help=_JSON_HELP)
    session_tag_cmd.set_defaults(func=_cmd_session_tag)
    session_report = session_sub.add_parser("report", help="summarise a session's activity")
    session_report.add_argument(
        "session_id",
        nargs="?",
        help="the session id to report on (omit when using --tag)",
    )
    session_report.add_argument(
        "--tag",
        metavar="TAG",
        help="aggregate all sessions sharing this tag",
    )
    session_report.add_argument("--json", action="store_true", help=_JSON_HELP)
    session_report.set_defaults(func=_cmd_session_report)
    session.set_defaults(func=_cmd_session)

    execution = sub.add_parser("execution", help="inspect detached (--detach) execution jobs")
    execution_sub = execution.add_subparsers(dest="execution_command")
    exec_status = execution_sub.add_parser("status", help="show a detached job's state")
    exec_status.add_argument("job_id", help="the execution id printed by `run --detach`")
    exec_status.add_argument("--json", action="store_true", help=_JSON_HELP)
    exec_status.set_defaults(func=_cmd_execution_status)
    exec_result = execution_sub.add_parser("result", help="print a finished job's output")
    exec_result.add_argument("job_id", help=_JOB_ID_HELP)
    exec_result.add_argument("--token", help=_TOKEN_HELP)
    exec_result.set_defaults(func=_cmd_execution_result)
    exec_watch = execution_sub.add_parser(
        "watch", help="replay a job's event log, following it live if still running"
    )
    exec_watch.add_argument("job_id", help=_JOB_ID_HELP)
    exec_watch.set_defaults(func=_cmd_execution_watch)
    exec_mat = execution_sub.add_parser(
        "materialize", help="write a finished job's generated files to a directory"
    )
    exec_mat.add_argument("job_id", help=_JOB_ID_HELP)
    exec_mat.add_argument(
        "--output-dir", required=True, help="directory to write the generated files into"
    )
    exec_mat.add_argument("--token", help=_TOKEN_HELP)
    exec_mat.set_defaults(func=_cmd_execution_materialize)
    exec_list = execution_sub.add_parser("list", help="list detached jobs and their states")
    exec_list.add_argument("--json", action="store_true", help=_JSON_HELP)
    exec_list.set_defaults(func=_cmd_execution_list)
    execution.set_defaults(func=_cmd_execution)

    init = sub.add_parser(
        "init",
        help="create the config file in the default location (if absent), then show the store",
    )
    init.set_defaults(func=_cmd_init)

    cfg = sub.add_parser("config", help="validate or inspect the resolved configuration")
    cfg_sub = cfg.add_subparsers(dest="config_command")

    cfg_validate = cfg_sub.add_parser(
        "validate",
        help="parse and validate the config file; exit non-zero on any error",
    )
    cfg_validate.add_argument("--json", action="store_true", help=_JSON_HELP)
    cfg_validate.set_defaults(func=_cmd_config_validate)

    cfg_show = cfg_sub.add_parser(
        "show",
        help="display the fully resolved configuration (default → file → env)",
    )
    cfg_show.add_argument(
        "--resolved",
        action="store_true",
        help="show each value with its source (always on; flag accepted for discoverability)",
    )
    cfg_show.add_argument("--json", action="store_true", help=_JSON_HELP)
    cfg_show.set_defaults(func=_cmd_config_show)

    cfg.set_defaults(func=_cmd_config)

    daemon = sub.add_parser("daemon", help="manage the generic-ml-cache HTTP daemon")
    daemon_sub = daemon.add_subparsers(dest="daemon_command")

    _daemon_host_port = {"host": "127.0.0.1", "port": 8765}

    daemon_start = daemon_sub.add_parser("start", help="start the HTTP daemon (foreground)")
    daemon_start.add_argument("--host", default=_daemon_host_port["host"], metavar="HOST")
    daemon_start.add_argument("--port", type=int, default=_daemon_host_port["port"], metavar="PORT")
    daemon_start.add_argument("--session", metavar="SESSION_ID", help="bind daemon to a session")
    daemon_start.add_argument("--metrics", action="store_true", help="enable Prometheus /metrics")
    daemon_start.set_defaults(func=_cmd_daemon_start)

    daemon_status = daemon_sub.add_parser("status", help="check if the daemon is running")
    daemon_status.add_argument("--host", default=_daemon_host_port["host"], metavar="HOST")
    daemon_status.add_argument(
        "--port", type=int, default=_daemon_host_port["port"], metavar="PORT"
    )
    daemon_status.add_argument("--json", action="store_true", help=_JSON_HELP)
    daemon_status.set_defaults(func=_cmd_daemon_status)

    daemon_stop = daemon_sub.add_parser("stop", help="send SIGTERM to a running daemon")
    daemon_stop.add_argument("--host", default=_daemon_host_port["host"], metavar="HOST")
    daemon_stop.add_argument("--port", type=int, default=_daemon_host_port["port"], metavar="PORT")
    daemon_stop.set_defaults(func=_cmd_daemon_stop)

    daemon.set_defaults(func=_cmd_daemon)

    status_line = sub.add_parser(
        "status-line",
        help="emit session stats as JSON for status-bar integrations",
    )
    status_line.add_argument(
        "--host", default=_daemon_host_port["host"], metavar="HOST", help="daemon host"
    )
    status_line.add_argument(
        "--port",
        type=int,
        default=_daemon_host_port["port"],
        metavar="PORT",
        help="daemon port",
    )
    status_line.add_argument(
        "--session",
        metavar="SESSION_ID",
        default=None,
        help="session to query (default: $GMLCACHE_SESSION)",
    )
    status_line.set_defaults(func=_cmd_status_line)

    return parser
