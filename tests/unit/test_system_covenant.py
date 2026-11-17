"""The covenant (api/system_covenant.py) is a byte-identical prefix — these
tests pin the bytes, the law count, and the witness's verdict on this repo.
No network, no model, no key is touched."""

from __future__ import annotations

import hashlib

from api.system_covenant import SPECROOF_COVENANT, covenant_prefix
from providers.base import LLMMessage

# sha256 of the covenant bytes as shipped — the pin the witness enforces.
PIN_SHA256 = "257a857782d8ea8f0b3af33792db2bcf685bedd577548a6be0986e143385418f"


def test_covenant_is_pinned_byte_for_byte() -> None:
    assert hashlib.sha256(SPECROOF_COVENANT.encode("utf-8")).hexdigest() == PIN_SHA256


def test_covenant_shape_holds() -> None:
    assert len(SPECROOF_COVENANT.encode("utf-8")) >= 1000
    laws = [
        ln for ln in SPECROOF_COVENANT.splitlines()
        if ln.startswith(("一、", "二、", "三、", "四、", "五、", "六、",
                          "七、", "八、", "九、", "十、", "十一、"))
    ]
    assert len(laws) == 11


def test_covenant_prefix_prepends_one_system_message() -> None:
    msgs = covenant_prefix([
        LLMMessage(role="system", content="lane-specific"),
        LLMMessage(role="user", content="q"),
    ])
    assert len(msgs) == 3
    assert msgs[0].role == "system"
    assert msgs[0].content == SPECROOF_COVENANT
    assert msgs[1].content == "lane-specific"


def test_lanes_carry_codex_then_covenant_exactly_once() -> None:
    """#1977: the byte-frozen codex rides first, the covenant rides behind it —
    always this order, never duplicated. Before #1977 the covenant stood alone
    at the head; the prefix sandwich changed deliberately and this pin moved
    with it (see `api/system_codex.py`)."""
    from api.system_codex import codex_for
    from api.ai_summary import _prompt as ai_prompt
    from api.insight_advice import _prompt as insight_prompt
    from api.observe_advice import _prompt as observe_prompt

    codex_zh = codex_for("zh")
    codex_en = codex_for("en")

    for prompt in (
        ai_prompt("{}"),
        insight_prompt("{}"),
        observe_prompt("zh", "{}"),
    ):
        assert prompt[0].content == codex_zh
        assert prompt[1].content == SPECROOF_COVENANT
    assert observe_prompt("en", "{}")[0].content == codex_en
    assert observe_prompt("en", "{}")[1].content == SPECROOF_COVENANT
    # never duplicated — exactly one codex, exactly one covenant per lane
    for prompt in (
        ai_prompt("{}"), insight_prompt("{}"),
        observe_prompt("zh", "{}"), observe_prompt("en", "{}"),
    ):
        codex_hits = sum(1 for m in prompt if m.content and codex_for("zh") in m.content or codex_for("en") in m.content)
        covenant_hits = sum(1 for m in prompt if m.content == SPECROOF_COVENANT)
        assert codex_hits == 1
        assert covenant_hits == 1


def test_covenant_witness_holds_on_this_repo() -> None:
    from agent.graphs.covenant_witness_graph import (
        build_covenant_witness_graph,
    )

    result = build_covenant_witness_graph().invoke({}) or {}
    assert result["verdict"] == "HELD"
    assert result["missing_paths"] == []
    assert result["laws"] == 11
    assert result["sha256"] == PIN_SHA256


def test_witness_detects_tampering(monkeypatch) -> None:  # noqa: ANN001
    from agent.graphs import covenant_witness_graph as mod

    monkeypatch.setattr(mod, "SPECROOF_COVENANT", mod.SPECROOF_COVENANT + "\n悄悄加一条\n")
    tampered = mod.intake_node({}) | mod.verify_node(mod.intake_node({}))
    assert tampered["verdict"] == "DRIFTED"
    assert tampered["pinned"] is False


def test_witness_pins_sha256_against_the_struck_covenant() -> None:
    from agent.graphs import covenant_witness_graph as mod

    assert mod.PIN_SHA256 == PIN_SHA256
    held = mod.verify_node(mod.intake_node({}))
    assert held["pinned"] is True
    assert held["verdict"] == "HELD"
