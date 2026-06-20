# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Optional configuration: defaults for ``run``, discovered from one INI file.

Three rules keep this predictable:

* **Opt-in.** :func:`load` reads the file only if it already exists and *never*
  writes it -- the cache works with no file present. :func:`write_default_config`
  (the ``gmlcache init`` command) writes one on explicit request, never on
  install or first run.
* **Overridable, with explicit precedence.** For ``mode`` and ``timeout`` the
  winner is, in order: a CLI flag, an environment variable, the config file, the
  built-in default. The ``store`` location is the exception -- config file or
  built-in default only, with **no flag and no environment** -- because where the
  cassettes live is the cache's own concern, not a per-call knob.
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
    # store defaults to the per-user data dir (XDG data home); set a path to change it
    store = /path/to/cassettes
    timeout = 120
    trust_scan = false

    [executables]
    claude = /opt/claude/bin/claude
    codex  = /usr/local/bin/codex

The optional ``[executables]`` section maps a client name to the path (or bare
command) used to launch it, supplying a persistent default for the per-call
``--executable`` seam. It is for installs that are not on ``PATH`` or for pinning
one of several builds; it never changes *which* client/model runs. Precedence per
client is ``--executable`` flag > ``[executables]`` config > the adapter's own
``PATH`` lookup. Unknown client keys are kept, not rejected (the adapter registry
is extensible), and a path is not validated at load -- a wrong path surfaces a
clear error only if and when that client is actually launched.

``trust_scan`` (boolean, default ``false``) governs whether an *allow-path* call
may be cached. Allow-path folders cannot be fingerprinted, so by default such a
call is passthrough (always fresh, never stored). Setting ``trust_scan = true``
asserts that the scanned folders are stable and lets these calls be cached like
any other -- on the ordinary key (the prompt already names the folder), with the
folders themselves never entering the key or the cassette. It is deliberately a
config/environment setting, not a per-call flag, because it trades soundness for
reuse and should be a considered, standing choice. Precedence is the usual
environment (``GMLCACHE_TRUST_SCAN``) > config file > built-in default.
"""

from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple

from .cache import Mode
from .common.errors import ConfigError

CONFIG_ENV = "GMLCACHE_CONFIG"
APP_DIR = "generic-ml-cache"
CONFIG_NAME = "config.ini"
SECTION = "defaults"
EXECUTABLES_SECTION = "executables"

#: built-in defaults; ``timeout`` of ``None`` means "no timeout". The store has
#: no static default here -- it resolves to :func:`default_store_path` (per-user
#: data dir) and has no flag/env layer, only the config file.
DEFAULTS: Dict[str, Optional[str]] = {"mode": "cache", "timeout": None}

_MODES = {m.value for m in Mode}

#: written by ``gmlcache init`` (and only then); ``{store}`` is filled with the
#: resolved per-user default so the user can see and edit where cassettes live.
_DEFAULT_CONFIG_TEMPLATE = """\
# generic-ml-cache configuration.
#
# Precedence for mode/timeout: CLI flag > environment > this file > built-in
# default. The STORE location is set only here -- there is no flag and no
# environment for it, because the store is the cache's own internal structure,
# not a per-call knob. To run a fully isolated cache, point GMLCACHE_CONFIG at a
# different config file: that selects a whole separate configuration (its own
# store, its own settings), which is a deliberate isolated instance rather than
# a per-call redirect.

[defaults]
mode = cache
# Where cassettes live. This is the per-user data dir by default; change freely.
store = {store}
# timeout = 120
trust_scan = false
# Optional cache size cap. Off by default = keep every cassette forever. When set
# (e.g. 5GB / 500MB / a byte count), the cache evicts the least-recently-used
# cassettes to make room as it records new ones. Time-based ("not used in N days")
# eviction arrives with daemon mode.
# max_size = 5GB

# Optional: pin a client's executable (off-PATH installs, or a specific build).
# [executables]
# claude = /opt/claude/bin/claude
# codex  = /usr/local/bin/codex
"""


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


def default_data_dir() -> Path:
    """The per-user data directory for this OS (XDG data home / %LOCALAPPDATA%)."""
    if os.name == "nt":
        base = (
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or str(Path.home() / "AppData" / "Local")
        )
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR


def default_store_path() -> Path:
    """Where cassettes live when the config does not say otherwise.

    The store is the cache's own internal structure, so its default sits in the
    per-user data directory (honoring ``XDG_DATA_HOME``), never in whatever
    directory the cache happens to be invoked from. There is deliberately no flag
    or environment override for the store *location*: a caller cannot redirect it
    per call, because that would fork the cache into per-caller copies and defeat
    the one thing a cache is for -- reuse. To run a fully isolated cache, point
    ``GMLCACHE_CONFIG`` at a different whole config file.
    """
    return default_data_dir() / "cassettes"


@dataclass
class FileConfig:
    """Settings read from the config file. ``source`` is the file actually read,
    or ``None`` when no file was present."""

    mode: Optional[str] = None
    store: Optional[str] = None
    timeout: Optional[float] = None
    trust_scan: Optional[bool] = None
    max_size: Optional[int] = None
    executables: Dict[str, str] = field(default_factory=dict)
    source: Optional[Path] = None


def _parse_timeout(raw: str, where: str) -> float:
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"invalid timeout {raw!r} {where}; expected a number") from exc


_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}

_SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}


def _parse_size(raw: str, where: str) -> int:
    """Parse a human size (``5GB``, ``500MB``, ``1048576``) into bytes (base 1024)."""
    text = raw.strip().lower().replace(" ", "")
    match = re.fullmatch(r"([0-9]*\.?[0-9]+)([a-z]*)", text)
    if not match:
        raise ConfigError(f"invalid size {raw!r} {where}; e.g. 5GB, 500MB, or a byte count")
    number, unit = match.group(1), match.group(2) or "b"
    if unit not in _SIZE_UNITS:
        raise ConfigError(
            f"invalid size unit {unit!r} {where}; expected one of {sorted(_SIZE_UNITS)}"
        )
    return int(float(number) * _SIZE_UNITS[unit])


def _parse_bool(raw: str, where: str) -> bool:
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ConfigError(f"invalid boolean {raw!r} {where}; expected true or false")


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

    trust_scan_raw = get("trust_scan")
    trust_scan = _parse_bool(trust_scan_raw, f"in {p}") if trust_scan_raw else None

    max_size_raw = get("max_size")
    max_size = _parse_size(max_size_raw, f"in {p}") if max_size_raw else None

    # [executables]: client name -> path/command. Kept verbatim and leniently
    # (unknown client keys are not an error -- the adapter registry is
    # extensible, and a key is only ever consulted when that client is run).
    executables = (
        {k: v for k, v in parser[EXECUTABLES_SECTION].items()}
        if parser.has_section(EXECUTABLES_SECTION)
        else {}
    )

    return FileConfig(
        mode=mode,
        store=get("store"),
        timeout=timeout,
        trust_scan=trust_scan,
        max_size=max_size,
        executables=executables,
        source=p,
    )


def write_default_config(path: Optional[Path] = None) -> Tuple[Path, bool]:
    """Create the config file with documented defaults, if it is absent.

    Returns ``(path, created)``; ``created`` is ``False`` when a file already
    existed (it is *never* overwritten). The generated file spells out the
    resolved default store path so the user can see -- and edit -- where the
    cassettes live. This is the only path that ever writes the config: ``load``
    still never creates it, so the cache keeps working with zero files present.
    """
    p = path or resolve_config_path()
    if p.is_file():
        return p, False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_DEFAULT_CONFIG_TEMPLATE.format(store=default_store_path()), encoding="utf-8")
    return p, True


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
    timeout_flag: Optional[float] = None,
) -> Dict[str, Tuple[object, str]]:
    """Resolve each setting to ``(value, source)`` by the documented precedence.

    ``source`` is one of ``flag`` / ``env`` / ``config`` / ``default`` so callers
    (notably ``status``) can show exactly why a value is what it is. The store is
    the exception: it has neither a flag nor an env layer (only ``config`` or
    ``default``), because its location is the cache's own, not a per-call knob.
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

    trust_env_raw = env.get("GMLCACHE_TRUST_SCAN")
    trust_env = _parse_bool(trust_env_raw, "in GMLCACHE_TRUST_SCAN") if trust_env_raw else None

    max_size_env_raw = env.get("GMLCACHE_MAX_SIZE")
    max_size_env = (
        _parse_size(max_size_env_raw, "in GMLCACHE_MAX_SIZE") if max_size_env_raw else None
    )

    return {
        "mode": _pick(mode_flag, mode_env, file_cfg.mode, DEFAULTS["mode"]),
        # store: config file or built-in per-user default only. No flag, no env --
        # a per-call store override would fork the cache and defeat reuse.
        "store": _pick(None, None, file_cfg.store, str(default_store_path())),
        "timeout": _pick(timeout_flag, timeout_env, file_cfg.timeout, DEFAULTS["timeout"]),
        # trust_scan has no CLI flag -- a standing, deliberate choice only.
        "trust_scan": _pick(None, trust_env, file_cfg.trust_scan, False),
        # max_size: off (None) by default = keep everything. Standing policy, so
        # config/env only, no per-call flag.
        "max_size": _pick(None, max_size_env, file_cfg.max_size, None),
    }


def executable_for(
    file_cfg: FileConfig, client: str, *, flag: Optional[str] = None
) -> Optional[str]:
    """The executable override to hand the adapter for ``client``.

    Precedence is ``--executable`` flag > ``[executables]`` config entry, and
    ``None`` when neither is set -- in which case the adapter falls back to its
    own ``PATH`` lookup. There is deliberately no environment layer here: a
    single variable cannot name *which* client, and per-client variables would
    be overkill for what this seam is for.
    """
    if flag is not None:
        return flag
    return file_cfg.executables.get(client)
