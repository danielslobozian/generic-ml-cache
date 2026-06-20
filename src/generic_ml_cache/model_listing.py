"""ModelListing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .adapters.base import ModelInfo


@dataclass
class ModelListing:
    """What discovery could learn about one client's available models.

    Three honest outcomes, never a guess:

    * absent client -> ``present=False`` (``supported`` is meaningless, left False);
    * present but no listing mechanism -> ``supported=False`` with a ``reason``;
    * present and listed -> ``supported=True`` and ``models`` populated (possibly
      empty if the client genuinely reported none).

    ``models`` is whatever the client relayed -- the cache invents nothing.
    """

    name: str
    present: bool
    supported: bool
    models: Optional[List[ModelInfo]] = None
    reason: Optional[str] = None
