# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import sys
from typing import List, Optional

from generic_ml_cache import register
from generic_ml_cache.application.port.out.base import ClientAdapter, ModelInfo
from generic_ml_cache.adapter.out.client.cursor import CursorAdapter
from generic_ml_cache.cli import main
from generic_ml_cache.application.domain.service.discover import list_models

# A trimmed sample of real `cursor-agent --list-models` output: a header line,
# ordinary entries, a "(current)"/"(default)" marker, and the trailing tip.
CURSOR_SAMPLE = """Available models

auto - Auto
gpt-5.3-codex-low - Codex 5.3 Low
composer-2.5 - Composer 2.5 (current)
composer-2.5-fast - Composer 2.5 Fast (default)
claude-opus-4-8-high - Opus 4.8 1M

Tip: use --model <id> (or /model <id> in interactive mode) to switch.
"""


def test_cursor_parse_model_list():
    models = CursorAdapter().parse_model_list(CURSOR_SAMPLE)
    ids = [m.id for m in models]
    # header + blank + Tip line are dropped; every real entry is kept.
    assert ids == [
        "auto",
        "gpt-5.3-codex-low",
        "composer-2.5",
        "composer-2.5-fast",
        "claude-opus-4-8-high",
    ]
    by_id = {m.id: m for m in models}
    assert by_id["auto"].name == "Auto"
    # markers are lifted into flags and stripped from the name
    assert by_id["composer-2.5"].current is True
    assert by_id["composer-2.5"].name == "Composer 2.5"
    assert by_id["composer-2.5-fast"].default is True
    assert by_id["composer-2.5-fast"].name == "Composer 2.5 Fast"


def test_list_models_unsupported_for_fake():
    # the 'fake' adapter inherits models_argv() -> None, so listing is unsupported
    ml = list_models("fake")
    assert ml.present is True
    assert ml.supported is False
    assert ml.models is None
    assert "no model-listing" in (ml.reason or "")


class _ListingAdapter(ClientAdapter):
    """A present client that can enumerate two models, via the interpreter."""

    name = "fakelist"
    default_executable = sys.executable

    def build_argv(self, *a, **k) -> List[str]:  # pragma: no cover - unused here
        raise NotImplementedError

    def models_argv(self, executable: str) -> Optional[List[str]]:
        return [executable, "-c", "print('m-one - Model One\\nm-two - Model Two (default)')"]

    def parse_model_list(self, stdout: str) -> List[ModelInfo]:
        out = []
        for line in stdout.splitlines():
            ident, _, label = line.partition(" - ")
            default = label.endswith("(default)")
            if default:
                label = label[: -len("(default)")].strip()
            out.append(ModelInfo(id=ident.strip(), name=label.strip(), default=default))
        return out


def test_list_models_success_relay():
    register(_ListingAdapter())
    ml = list_models("fakelist")
    assert ml.present is True and ml.supported is True
    assert [m.id for m in ml.models] == ["m-one", "m-two"]
    assert ml.models[1].default is True


def test_models_cli_json_is_valid_even_when_unsupported(capsys):
    rc = main(["models", "fake", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)  # must parse, per the always-valid-JSON rule
    assert isinstance(payload, list) and len(payload) == 1
    assert payload[0]["name"] == "fake"
    assert payload[0]["supported"] is False
    assert payload[0]["models"] is None
