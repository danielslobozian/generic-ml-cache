# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""Gemini thinking-config translation layer.

Gemini has two distinct control surfaces for reasoning effort, split by model
generation:

* **Gemini 2.5 series** — ``thinkingConfig.thinkingBudget`` (integer token
  count). Thinking is on by default for pro/flash; off by default for
  flash-lite. Budget 0 disables thinking entirely.
* **Gemini 3.x and later** — ``thinkingConfig.thinkingLevel`` (enum string:
  ``"minimal"``, ``"low"``, ``"medium"``, ``"high"``).

The two are mutually exclusive per request. 3.x models accept thinkingBudget
for backwards compatibility but Google warns it may cause unexpected behaviour,
so we always use thinkingLevel for 3.x.

Source: https://ai.google.dev/gemini-api/docs/thinking
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class GeminiEffortType(Enum):
    """Which thinkingConfig field a model generation uses."""

    LEVEL = "level"  # thinkingLevel: str  — Gemini 3.x+
    BUDGET = "budget"  # thinkingBudget: int — Gemini 2.5


# Effort strings our system understands → thinkingBudget token counts for
# 2.5 models. Values chosen to spread across the 0–32768 documented range:
# low ≈ 3 %, medium ≈ 25 %, high ≈ 75 %.
_LEVEL_TO_BUDGET: Dict[str, int] = {
    "low": 1024,
    "medium": 8192,
    "high": 24576,
}

# Explicit list of model base-names that use thinkingBudget (2.5 family).
# Strip the "models/" prefix and any version suffix (e.g. "-001") before
# matching. Extend this list when Google releases new 2.5-generation models.
# Source: https://ai.google.dev/gemini-api/docs/thinking
_BUDGET_MODEL_BASES: frozenset = frozenset(
    {
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-preview",
        "gemini-2.5-flash-image",
        "gemini-2.5-computer-use-preview",
        "gemini-robotics-er-1.5-preview",
        "gemini-robotics-er-1.6-preview",
    }
)


def _effort_type_for_model(model: str) -> GeminiEffortType:
    """Return the effort type for ``model`` by consulting the known list.

    The model name may carry a ``models/`` prefix (from the API) and a version
    suffix (``-001``, ``-10-2025``, etc.); both are stripped before matching.
    Anything not in the budget list is assumed to be 3.x+ and uses LEVEL.
    """
    base = model.removeprefix("models/")
    # Strip trailing version fragments: "-001", "-preview", date suffixes, …
    # Match greedily against the known base names instead of guessing the suffix
    # pattern, so new versioned releases are handled correctly once their base
    # name is in the list.
    for known in _BUDGET_MODEL_BASES:
        if base == known or base.startswith(known + "-"):
            return GeminiEffortType.BUDGET
    return GeminiEffortType.LEVEL


@dataclass(frozen=True)
class GeminiThinkingConfig:
    """Gemini thinkingConfig ready to embed in a generateContent body.

    Build via :meth:`from_effort` — never construct directly. The ``to_dict``
    method returns the ``thinkingConfig`` object to nest inside
    ``generationConfig``; the caller wraps it:
    ``body["generationConfig"] = {"thinkingConfig": config.to_dict()}``.
    """

    effort_type: GeminiEffortType
    level: str = ""
    budget: int = 0

    @classmethod
    def from_effort(cls, effort: str, model: str) -> "GeminiThinkingConfig":
        """Translate our generic ``effort`` string for ``model``.

        For budget models: named levels (``"low"``, ``"medium"``, ``"high"``)
        map to predefined token counts; a digit string is parsed as a raw token
        count (e.g. ``"2048"`` → thinkingBudget 2048).
        For level models: the effort string is forwarded verbatim as
        thinkingLevel (``"low"``, ``"medium"``, ``"high"``, ``"minimal"``).
        """
        effort_type = _effort_type_for_model(model)
        if effort_type is GeminiEffortType.BUDGET:
            if effort.isdigit():
                return cls(effort_type=effort_type, budget=int(effort))
            return cls(
                effort_type=effort_type,
                budget=_LEVEL_TO_BUDGET.get(effort, _LEVEL_TO_BUDGET["medium"]),
            )
        return cls(effort_type=effort_type, level=effort)

    @property
    def is_budget(self) -> bool:
        return self.effort_type is GeminiEffortType.BUDGET

    def to_dict(self) -> Dict[str, Any]:
        """Return the ``thinkingConfig`` dict to embed in ``generationConfig``."""
        if self.is_budget:
            return {"thinkingBudget": self.budget}
        return {"thinkingLevel": self.level}
