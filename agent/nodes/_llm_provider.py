"""The LLM provider the LLM-using nodes ask for, or ``None`` when unconfigured.

``generate_counterexamples`` and ``compile_contracts`` each carried their own
factory (#498, #503), and they did not agree on **where the API key comes
from**: the first read ``os.getenv("LLM_API_KEY")`` while the second read
``providers.config.load_model_config()`` — the canonical source, which reads the
model-settings file the UI writes *and* lets the environment override it.

So a key configured through the settings UI reached contract compilation and
silently did not reach counterexample generation, which fell back to the
deterministic template with no error and no note.

(``review_court`` carried a third copy, but it was dead code — the court takes
its provider as an argument via ``build_llm_defense_producer``. That copy was
removed in #499; this module serves the two live consumers.)
"""
from __future__ import annotations

from typing import Any


def get_provider() -> Any:
    """An OpenAI-compatible provider, or ``None`` when no key is configured.

    The key comes from :func:`providers.config.load_model_config` — the same
    source the settings UI and the CLI write — so "configured" means the same
    thing in every node. An unreadable or invalid config file degrades to
    ``None`` rather than taking the node down: every caller has a deterministic
    path for that case, and a crash here would lose the whole run.
    """
    from providers.config import load_model_config

    try:
        api_key = load_model_config()["api_key"]
    except Exception:  # noqa: BLE001 — an unreadable config means "not configured"
        return None
    if not api_key or api_key == "replace_me":
        return None
    try:
        from providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(probe_on_init=False)
    except Exception:  # noqa: BLE001 — an unavailable provider degrades to None
        return None


__all__ = ["get_provider"]
