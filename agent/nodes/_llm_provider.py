"""The LLM provider both LLM-using nodes ask for, or ``None`` when unconfigured.

``generate_counterexamples`` and ``review_court`` carried identical copies
(#498). Both want the same three decisions: no key (or the placeholder key the
example env ships) means no provider; the provider is constructed with
``probe_on_init=False`` so building it never makes a network call; and any
construction failure degrades to ``None`` rather than taking the node down.

Keeping them apart meant a fix to any of those three could reach one node and
not the other, and a node that silently lost its provider falls back to a
weaker path without saying so.
"""
from __future__ import annotations

import os
from typing import Any


def get_provider() -> Any:
    """An OpenAI-compatible provider, or ``None`` when no key is configured."""
    api_key = os.getenv("LLM_API_KEY", "")
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(probe_on_init=False)
    except Exception:  # noqa: BLE001 — an unavailable provider degrades to None
        return None


__all__ = ["get_provider"]
