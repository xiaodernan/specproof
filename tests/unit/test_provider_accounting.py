"""Budget partitions and routing configuration must match actual API semantics."""
import json

import pytest

from craft.cost import cost_of_usage
from providers.budget import TokenBudget
from providers.config import load_model_config
from providers.openai_compatible import OpenAICompatibleProvider
from providers.responses_protocol import usage_data


def test_reasoning_and_cache_are_subsets_not_extra_tokens():
    usage = usage_data({
        "input_tokens": 100, "output_tokens": 80, "total_tokens": 180,
        "input_tokens_details": {"cached_tokens": 40},
        "output_tokens_details": {"reasoning_tokens": 60},
    })
    budget = TokenBudget(1000, cost_weights={"cache_hit": 1})
    entry = budget.record(usage)
    assert entry["charge"] == 180
    assert entry["prompt_cache_miss_tokens"] == 60
    assert entry["reasoning_tokens"] == 60
    cost = cost_of_usage(usage, dict.fromkeys((
        "prompt_cache_hit", "prompt_cache_miss", "completion", "reasoning",
    ), 1))
    assert cost["total_usd"] == 0.000180


def test_partitions_are_clamped_to_totals():
    budget = TokenBudget(1000, cost_weights={"cache_hit": 1})
    assert budget.charge(10, 20, 999, 999, 999) == 30
    assert budget.record({"prompt_tokens": -100, "completion_tokens": -10})["charge"] == 0


def test_environment_route_never_borrows_private_key(monkeypatch, tmp_path):
    cfg = tmp_path / "llm.json"
    cfg.write_text(json.dumps({"base_url": "https://old.test/v1", "api_key": "old-key",
                               "model": "old", "protocol": "responses"}))
    monkeypatch.setenv("SPECPROOF_MODEL_CONFIG", str(cfg))
    monkeypatch.setenv("LLM_BASE_URL", "https://new.test")
    monkeypatch.setenv("LLM_MODEL", "gpt-6-astra")
    result = load_model_config()
    assert result["api_key"] == ""
    assert result["protocol"] == "responses"
    assert result["base_url"] == "https://new.test/v1"


def test_explicit_empty_key_is_not_replaced_with_saved_secret(monkeypatch, tmp_path):
    cfg = tmp_path / "llm.json"
    cfg.write_text(json.dumps({"base_url": "https://old.test/v1", "api_key": "old-key"}))
    monkeypatch.setenv("SPECPROOF_MODEL_CONFIG", str(cfg))
    monkeypatch.setenv("LLM_API_KEY", "")
    assert load_model_config()["api_key"] == ""


def test_empty_reasoning_means_model_default(monkeypatch):
    provider = OpenAICompatibleProvider(
        base_url="https://example.test", api_key="fake", model="gpt-6-astra",
        protocol="responses", reasoning_effort="",
    )
    assert provider.reasoning_effort == ""


def test_broken_local_config_does_not_block_complete_environment(monkeypatch, tmp_path):
    cfg = tmp_path / "llm.json"
    cfg.write_text("not-json")
    monkeypatch.setenv("SPECPROOF_MODEL_CONFIG", str(cfg))
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test")
    monkeypatch.setenv("LLM_API_KEY", "env-test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-6-astra")
    assert load_model_config()["api_key"] == "env-test-key"


@pytest.mark.parametrize("invalid", [None, [], 42])
def test_malformed_config_values_fail_clearly(monkeypatch, tmp_path, invalid):
    cfg = tmp_path / "llm.json"
    cfg.write_text(json.dumps({"api_key": invalid}))
    monkeypatch.setenv("SPECPROOF_MODEL_CONFIG", str(cfg))
    with pytest.raises(ValueError, match="配置字段"):
        load_model_config()

def test_cancelling_model_call_stops_pending_request():
    import asyncio
    import threading

    from craft.llm import LLMClient, LLMUnavailableError
    from providers.base import LLMMessage

    entered, finished = threading.Event(), threading.Event()
    class SlowProvider:
        async def chat(self, *args, **kwargs):
            entered.set()
            try:
                await asyncio.sleep(60)
            finally:
                finished.set()
        async def close(self):
            pass
    client = LLMClient(provider=SlowProvider())
    errors = []
    def invoke():
        try:
            client.chat_sync([LLMMessage(role="user", content="test")], label="cancel")
        except LLMUnavailableError as exc:
            errors.append(exc)
    thread = threading.Thread(target=invoke)
    thread.start()
    try:
        # Generous ceilings: the provider sleeps 60s and cancel() must abort it,
        # so a thread that survives these waits is a real failure — the ceilings
        # only absorb event-loop / thread scheduling latency on a loaded host.
        assert entered.wait(10)
        client.cancel()
        thread.join(10)
        assert not thread.is_alive()
        assert finished.wait(10)
        assert errors
    finally:
        client.close()
