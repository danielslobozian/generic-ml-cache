# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Controller: config sub-commands — validate, show."""

from __future__ import annotations

import argparse
import sys

from generic_ml_cache_core.common.errors import ConfigError

from generic_ml_cache_cli import config


def _cmd_config(args: argparse.Namespace) -> int:
    print("usage: gmlcache config <validate|show>", file=sys.stderr)
    return 1


def _cmd_config_validate(args: argparse.Namespace) -> int:
    from generic_ml_cache_cli.config import validate

    path = config.resolve_config_path()
    issues = validate(path)

    errors = [i for i in issues if i.severity == "error"]

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "config_path": str(path),
                    "present": path.is_file(),
                    "valid": len(errors) == 0,
                    "issues": [
                        {"severity": i.severity, "key": i.key, "message": i.message} for i in issues
                    ],
                },
                indent=2,
            )
        )
        return 0 if not errors else 4

    if not path.is_file():
        print(f"config: {path}  (not present — defaults apply, no validation needed)")
        return 0

    if not issues:
        print(f"config: {path}  OK")
        return 0

    for issue in issues:
        key_part = f"{issue.key}: " if issue.key else ""
        print(f"{issue.severity}: {key_part}{issue.message}")

    return 4 if errors else 0


def _cmd_config_show(args: argparse.Namespace) -> int:
    try:
        file_cfg = config.load()
        settings = config.resolve_settings(file_cfg)
    except ConfigError as exc:
        print(f"gmlc: {exc}", file=sys.stderr)
        return 4

    path = config.resolve_config_path()

    if args.json:
        import json

        print(
            json.dumps(
                {
                    "config_path": str(path),
                    "loaded": file_cfg.source is not None,
                    "settings": {k: {"value": v[0], "source": v[1]} for k, v in settings.items()},
                    "executables": dict(file_cfg.executables),
                },
                indent=2,
            )
        )
        return 0

    print(f"config file : {path}  ({'loaded' if file_cfg.source else 'not present'})")
    print()
    print("resolved settings  (resolution order: default → file → env — no run flags applied)")
    for key, (value, source) in settings.items():
        shown: object = "none" if value is None else value
        if isinstance(shown, bool):
            shown = "true" if shown else "false"
        print(f"  {key:<12} {str(shown):<24} (from {source})")
    if file_cfg.executables:
        print()
        print("executables (from config):")
        for client, exe in sorted(file_cfg.executables.items()):
            print(f"  {client:<8} {exe}")
    return 0
