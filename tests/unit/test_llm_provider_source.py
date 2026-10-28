"""#503 — one provider factory, and the API key comes from the canonical source.

Two nodes used to build the LLM provider themselves. ``generate_counterexamples``
read ``os.getenv("LLM_API_KEY")``; ``compile_contracts`` read
``providers.config.load_model_config()`` — which reads the **model-settings file
the UI writes** and lets the environment override it. A key configured through
the UI therefore reached contract compilation and silently did not reach
counterexample generation: it fell back to the deterministic template with no
error and no note.

(``review_court`` had a third copy that was dead code — the court takes its
provider as an argument. It was removed in #499.)

These tests pin the canonical source and the degradation rules.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.nodes._llm_provider import get_provider

_ENV_NAMES = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL", "SPECPROOF_MODEL_CONFIG")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def _config_file(tmp_path: Path, payload: dict[str, str]) -> Path:
    path = tmp_path / "llm.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_a_key_from_the_settings_file_reaches_the_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # This is the case that used to fail: no env var, key only in the file the
    # settings UI writes.
    monkeypatch.setenv(
        "SPECPROOF_MODEL_CONFIG",
        str(_config_file(tmp_path, {"api_key": "sk-from-file", "base_url": "https://llm.example/v1"})),
    )
    assert get_provider() is not None


def test_no_key_anywhere_means_no_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECPROOF_MODEL_CONFIG", str(_config_file(tmp_path, {})))
    assert get_provider() is None


def test_the_placeholder_key_means_no_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "SPECPROOF_MODEL_CONFIG", str(_config_file(tmp_path, {"api_key": "replace_me"}))
    )
    assert get_provider() is None


def test_the_environment_overrides_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # An explicit empty env value clears the credential on purpose.
    monkeypatch.setenv(
        "SPECPROOF_MODEL_CONFIG",
        str(_config_file(tmp_path, {"api_key": "sk-from-file"})),
    )
    monkeypatch.setenv("LLM_API_KEY", "")
    assert get_provider() is None


def test_a_malformed_config_degrades_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # load_model_config raises on an unreadable file; the factory must not let
    # that take the node down.
    bad = tmp_path / "llm.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("SPECPROOF_MODEL_CONFIG", str(bad))
    assert get_provider() is None


def test_the_two_live_consumers_share_one_factory() -> None:
    import agent.nodes.compile_contracts as compile_contracts
    import agent.nodes.generate_counterexamples as generate_counterexamples

    assert (
        compile_contracts._get_provider
        is generate_counterexamples._get_provider
        is get_provider
    )


def test_review_court_takes_its_provider_as_an_argument() -> None:
    # The court does not build a provider: `build_llm_defense_producer(provider)`
    # is handed one. Its old `_get_provider` was dead code (defined, never
    # called) and is gone, so it must not be re-introduced as a factory.
    import agent.nodes.review_court as review_court

    assert not hasattr(review_court, "_get_provider")
    assert callable(review_court.build_llm_defense_producer)
