"""ProbeResult."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .cassette import Cassette
from .probe_status import ProbeStatus


@dataclass
class ProbeResult:
    """What a probe found, without running or recording anything.

    ``cassette`` carries the matched recording on a ``HIT`` (so a caller can read
    its metadata and recorded usage) and is ``None`` otherwise.
    """

    status: ProbeStatus
    cassette: Optional[Cassette] = None
