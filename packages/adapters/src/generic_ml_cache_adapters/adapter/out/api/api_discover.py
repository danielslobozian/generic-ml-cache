# SPDX-FileCopyrightText: 2026 Daniel Slobozian
# SPDX-License-Identifier: Apache-2.0
"""API provider discovery: list models for a registered API provider.

Advisory and read-only — mirrors the client discover module but for direct
REST adapters (Gemini, Anthropic, OpenAI …) rather than local CLI clients.
The adapter reads its own API key from the environment when ``api_key`` is not
passed explicitly.
"""

from __future__ import annotations

from typing import FrozenSet, Optional

from generic_ml_cache_core.application.domain.model.model_listing import ModelListing
from generic_ml_cache_core.application.port.out.model_listing_port import ModelListingPort
from generic_ml_cache_core.common.errors import UnknownClient

from generic_ml_cache_adapters.discovery.composition import get_adapter


def list_api_models(
    provider: str,
    api_key: Optional[str] = None,
    whitelist: Optional[FrozenSet[str]] = None,
) -> ModelListing:
    """List models for a registered API provider.

    Returns a :class:`ModelListing` in all cases — never raises for an absent or
    unsupported provider. Three honest outcomes:

    * unknown provider → ``present=False``
    * provider registered but adapter does not implement ModelListingPort →
      ``supported=False``
    * provider listed → ``supported=True`` and ``models`` populated

    ``api_key`` is accepted for backward compatibility; adapters resolve their
    key from the environment when it is not passed.
    """
    try:
        adapter = get_adapter(provider, whitelist=whitelist)
    except UnknownClient as exc:
        return ModelListing(name=provider, present=False, supported=False, reason=str(exc))

    if not isinstance(adapter, ModelListingPort):
        return ModelListing(
            name=provider,
            present=True,
            supported=False,
            reason="this provider has no model-listing endpoint",
        )

    try:
        models = adapter.list_models()
    except Exception as exc:  # noqa: BLE001 — any transport failure → honest error
        return ModelListing(
            name=provider,
            present=True,
            supported=True,
            reason=f"model listing failed: {exc}",
        )

    return ModelListing(name=provider, present=True, supported=True, models=models)
