"""Unit tests for providers.router.ModelRouter — no network, no Docker.

The router reads a pure env mapping (injected), so no process environment
touching is needed except the one test that proves the default source is
os.environ.
"""

import logging

from providers.router import (
    CHEAP_TASK_KINDS,
    ENV_CHEAP_BASE_URL,
    ENV_CHEAP_MODEL,
    ENV_LLM_BASE_URL,
    ENV_LLM_MODEL,
    ENV_STRONG_BASE_URL,
    ENV_STRONG_MODEL,
    KNOWN_TASK_KINDS,
    STRONG_TASK_KINDS,
    ModelRouter,
    ProviderRoute,
)


def _env(**overrides: str) -> dict[str, str]:
    base = {
        ENV_LLM_BASE_URL: "http://strong.example",
        ENV_LLM_MODEL: "strong-model",
    }
    base.update(overrides)
    return base


class TestRoutingTableDefaults:
    def test_no_router_config_routes_everything_to_strong(self) -> None:
        router = ModelRouter(env=_env())
        assert not router.cheap_enabled
        assert router.configured_tiers() == frozenset({"strong"})
        for kind in (
            "draft",
            "diagnose",
            "edit_plan",
            "court",
            "counterexample",
            "accept_judge",
            "contract_compile",
            "mystery_kind",
            "",
        ):
            route = router.route(kind)
            assert route.tier == "strong", kind
            assert route.base_url == "http://strong.example"
            assert route.model == "strong-model"
            assert not route.is_fallback

    def test_metrics_reflect_strong_only(self) -> None:
        router = ModelRouter(env=_env())
        router.route("court")
        metrics = router.metrics()
        assert metrics["router_configured"] is False
        assert metrics["configured_tiers"] == ["strong"]
        assert metrics["cheap"] is None
        assert metrics["strong"] == {
            "base_url": "http://strong.example",
            "model": "strong-model",
        }
        assert metrics["route_counts"] == {"cheap": 0, "strong": 1}
        assert metrics["fallback_count"] == 0


class TestEnvParsing:
    def test_cheap_env_enables_cheap_tier_for_mechanical_kinds(self) -> None:
        router = ModelRouter(
            env=_env(
                **{
                    ENV_CHEAP_BASE_URL: "http://cheap.example",
                    ENV_CHEAP_MODEL: "cheap-model",
                }
            )
        )
        assert router.cheap_enabled
        assert router.configured_tiers() == frozenset({"cheap", "strong"})
        for kind in ("draft", "diagnose", "edit_plan"):
            route = router.route(kind)
            assert route == ProviderRoute(
                tier="cheap", base_url="http://cheap.example", model="cheap-model"
            )

    def test_judgment_and_unknown_kinds_stay_strong_even_with_cheap(self) -> None:
        router = ModelRouter(
            env=_env(
                **{
                    ENV_CHEAP_BASE_URL: "http://cheap.example",
                    ENV_CHEAP_MODEL: "cheap-model",
                }
            )
        )
        for kind in ("court", "counterexample", "accept_judge", "contract_compile"):
            assert router.route(kind).tier == "strong"
        assert router.route("totally_unknown").tier == "strong"

    def test_partial_cheap_config_disables_cheap_tier(self, caplog) -> None:
        with caplog.at_level(logging.WARNING, logger="providers.router"):
            router = ModelRouter(env=_env(**{ENV_CHEAP_BASE_URL: "http://only-base"}))
        assert not router.cheap_enabled
        assert router.route("draft").tier == "strong"
        assert any("partial" in record.message for record in caplog.records)

    def test_strong_env_overrides_llm_env_per_field(self) -> None:
        router = ModelRouter(
            env=_env(
                **{
                    ENV_STRONG_BASE_URL: "http://strong2.example",
                    ENV_STRONG_MODEL: "strong2-model",
                }
            )
        )
        route = router.route("court")
        assert route.base_url == "http://strong2.example"
        assert route.model == "strong2-model"

    def test_strong_model_only_keeps_llm_base_url(self) -> None:
        router = ModelRouter(env=_env(**{ENV_STRONG_MODEL: "only-model"}))
        route = router.route("court")
        assert route.base_url == "http://strong.example"
        assert route.model == "only-model"

    def test_strong_model_defaults_to_deepseek_v4_pro(self) -> None:
        router = ModelRouter(env={})
        assert router.route("court").model == "deepseek-v4-pro"
        assert router.route("court").base_url == ""

    def test_constructor_reads_process_environment_by_default(self, monkeypatch) -> None:
        monkeypatch.setenv(ENV_CHEAP_BASE_URL, "http://env-cheap.example")
        monkeypatch.setenv(ENV_CHEAP_MODEL, "env-cheap-model")
        router = ModelRouter()
        assert router.cheap_enabled
        assert router.route("draft").tier == "cheap"


class TestCheapToStrongFallback:
    def test_cheap_failure_falls_back_to_strong_and_counts(self, caplog) -> None:
        router = ModelRouter(
            env=_env(
                **{
                    ENV_CHEAP_BASE_URL: "http://cheap.example",
                    ENV_CHEAP_MODEL: "cheap-model",
                }
            )
        )
        cheap_route = router.route("draft")
        assert cheap_route.tier == "cheap"
        with caplog.at_level(logging.WARNING, logger="providers.router"):
            strong_route = router.on_failure(cheap_route)
        assert strong_route == ProviderRoute(
            tier="strong",
            base_url="http://strong.example",
            model="strong-model",
            is_fallback=True,
        )
        assert router.fallback_count == 1
        assert router.metrics()["fallback_count"] == 1
        assert any(
            "falling back to strong" in record.message for record in caplog.records
        )

    def test_strong_failure_is_a_noop(self, caplog) -> None:
        router = ModelRouter(env=_env())
        strong_route = router.route("court")
        with caplog.at_level(logging.WARNING, logger="providers.router"):
            again = router.on_failure(strong_route)
        assert again is strong_route
        assert router.fallback_count == 0
        assert caplog.records == []

    def test_fallback_route_kwargs_match_strong_config(self) -> None:
        router = ModelRouter(
            env=_env(
                **{
                    ENV_CHEAP_BASE_URL: "http://cheap.example",
                    ENV_CHEAP_MODEL: "cheap-model",
                }
            )
        )
        fallback = router.on_failure(router.route("edit_plan"))
        assert fallback.as_provider_kwargs() == {
            "base_url": "http://strong.example",
            "model": "strong-model",
        }

    def test_empty_route_config_passes_none_to_provider(self) -> None:
        route = ProviderRoute(tier="strong", base_url="", model="")
        assert route.as_provider_kwargs() == {"base_url": None, "model": None}


def test_known_kind_partition_matches_captain_table() -> None:
    assert frozenset({"draft", "diagnose", "edit_plan"}) == CHEAP_TASK_KINDS
    assert frozenset(
        {"court", "counterexample", "accept_judge", "contract_compile"}
    ) == STRONG_TASK_KINDS
    assert KNOWN_TASK_KINDS == CHEAP_TASK_KINDS | STRONG_TASK_KINDS


def test_route_counts_increment_per_call() -> None:
    router = ModelRouter(
        env=_env(
            **{
                ENV_CHEAP_BASE_URL: "http://cheap.example",
                ENV_CHEAP_MODEL: "cheap-model",
            }
        )
    )
    router.route("draft")
    router.route("diagnose")
    router.route("court")
    router.route("unknown")
    assert router.route_counts == {"cheap": 2, "strong": 2}


def test_route_is_case_and_whitespace_insensitive() -> None:
    router = ModelRouter(
        env=_env(
            **{
                ENV_CHEAP_BASE_URL: "http://cheap.example",
                ENV_CHEAP_MODEL: "cheap-model",
            }
        )
    )
    assert router.route("  Draft ").tier == "cheap"
    assert router.route("COURT").tier == "strong"
