# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Optional configuration: defaults for ``run``, discovered from one INI file.

Three rules keep this predictable:

* **Opt-in.** The file is read only if it already exists. It is *never* written
  on install or on first run -- the cache has no opinion about creating it.
* **Overridable, with explicit precedence.** For each setting the winner is, in
  order: a CLI flag, then an environment variable, then the config file, then the
  built-in default.
* **Zero dependencies.** The format is INI (stdlib :mod:`configparser`) and the
  per-user location is resolved inline, so nothing beyond the standard library is
  needed on any supported Python.

Location (override everything with ``GMLCACHE_CONFIG=/path/to/file``):

* Windows -- ``%APPDATA%\\generic-ml-cache\\config.ini``
* otherwise -- ``$XDG_CONFIG_HOME/generic-ml-cache/config.ini`` (or
  ``~/.config/generic-ml-cache/config.ini``)

File shape::

    [defaults]
    mode = cache
    store = .gmlcache
    timeout = 120
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from .cache import Mode
from .errors import ConfigError

CONFIG_ENV = "GMLCACHE_CONFIG"
APP_DIR = "generic-ml-cache"
CONFIG_NAME = "config.ini"
SECTION = "defaults"

#: built-in defaults; ``timeout`` of ``None`` means "no timeout"
DEFAULTS: Dict[str, Optional[str]] = {"mode": "cache", "store": ".gmlcache", "timeout": None}

_MODES = {m.value for m in Mode}


def default_config_path() -> Path:
    """The per-user config path for this OS, ignoring the env override."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_DIR / CONFIG_NAME


def resolve_config_path() -> Path:
    """Where the config file would be read from: env override, else OS default."""
    override = os.environ.get(CONFIG_ENV)
    return Path(override) if override else default_config_path()


@dataclass
class FileConfig:
    """Settings read from the config file. ``source`` is the file actually read,
    or ``None`` when no file was present."""

    mode: Optional[str] = None
    store: Optional[str] = None
    timeout: Optional[float] = None
    source: Optional[Path] = None


def _parse_timeout(raw: str, where: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"invalid timeout {raw!r} {where}; expected a number") from exc


def load(path: Optional[Path] = None) -> FileConfig:
    """Read the config file if it exists; a missing file yields empty defaults."""
    p = path or resolve_config_path()
    if not p.is_file():
        return FileConfig()

    parser = configparser.ConfigParser()
    try:
        parser.read(p, encoding="utf-8")
    except configparser.Error as exc:
        raise ConfigError(f"could not parse config at {p}: {exc}") from exc

    section = parser[SECTION] if parser.has_section(SECTION) else None

    def get(key: str) -> Optional[str]:
        return section.get(key) if section is not None else None

    mode = get("mode")
    if mode is not None and mode not in _MODES:
        raise ConfigError(f"invalid mode {mode!r} in {p}; expected one of {sorted(_MODES)}")

    timeout_raw = get("timeout")
    timeout = _parse_timeout(timeout_raw, f"in {p}") if timeout_raw else None

    return FileConfig(mode=mode, store=get("store"), timeout=timeout, source=p)


def _pick(flag, env, file_value, default) -> Tuple[object, str]:
    """First non-empty of flag > env > file > default, with its provenance."""
    if flag is not None:
        return flag, "flag"
    if env is not None and env != "":
        return env, "env"
    if file_value is not None:
        return file_value, "config"
    return default, "default"


def resolve_settings(
    file_cfg: FileConfig,
    *,
    mode_flag: Optional[str] = None,
    store_flag: Optional[str] = None,
    timeout_flag: Optional[float] = None,
) -> Dict[str, Tuple[object, str]]:
    """Resolve each setting to ``(value, source)`` by the documented precedence.

    ``source`` is one of ``flag`` / ``env`` / ``config`` / ``default`` so callers
    (notably ``status``) can show exactly why a value is what it is.
    """
    env = os.environ

    mode_env = env.get("GMLCACHE_MODE")
    if mode_env and mode_env not in _MODES:
        raise ConfigError(
            f"invalid mode {mode_env!r} in GMLCACHE_MODE; expected one of {sorted(_MODES)}"
        )

    timeout_env_raw = env.get("GMLCACHE_TIMEOUT")
    timeout_env = (
        _parse_timeout(timeout_env_raw, "in GMLCACHE_TIMEOUT") if timeout_env_raw else None
    )

    return {
        "mode": _pick(mode_flag, mode_env, file_cfg.mode, DEFAULTS["mode"]),
        "store": _pick(store_flag, env.get("GMLCACHE_STORE"), file_cfg.store, DEFAULTS["store"]),
        "timeout": _pick(timeout_flag, timeout_env, file_cfg.timeout, DEFAULTS["timeout"]),
    }
