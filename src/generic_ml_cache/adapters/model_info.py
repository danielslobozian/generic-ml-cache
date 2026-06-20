"""ModelInfo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelInfo:
    """One model a client reports it can use. Purely what the client relayed.

    ``id`` is the string a caller would pass as ``--model``; ``name`` is the
    client's own human label. ``default``/``current`` mirror any marker the
    client printed. The cache neither invents nor validates these fields.
    """

    id: str
    name: str
    default: bool = False
    current: bool = False
