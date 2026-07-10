"""Unit tests for LLM providers."""


from providers.base import LLMMessage, LLMResponse
from providers.probe_result import ProbeResult


class TestProbeResult:
    def test_all_passed_when_all_true(self) -> None:
        caps = dict.fromkeys(ProbeResult.CAPABILITY_KEYS, True)
        pr = ProbeResult(
            provider="test",
            base_url="http://test",
            model="test-model",
            capabilities=caps,
        )
        assert pr.all_passed()

    def test_all_passed_fails_when_one_false(self) -> None:
        caps = dict.fromkeys(ProbeResult.CAPABILITY_KEYS, True)
        caps["tool_calls"] = False
        pr = ProbeResult(
            provider="test",
            base_url="http://test",
            model="test-model",
            capabilities=caps,
        )
        assert not pr.all_passed()

    def test_passed_individual(self) -> None:
        pr = ProbeResult(
            provider="test",
            base_url="http://test",
            model="test",
            capabilities={"chat": True, "streaming": False},
        )
        assert pr.passed("chat")
        assert not pr.passed("streaming")

    def test_summary_includes_pass_fail(self) -> None:
        caps = {k: i % 2 == 0 for i, k in enumerate(ProbeResult.CAPABILITY_KEYS)}
        pr = ProbeResult(
            provider="test",
            base_url="http://test",
            model="test",
            capabilities=caps,
        )
        summary = pr.summary()
        assert "PASS" in summary
        assert "FAIL" in summary

    def test_errors_in_summary(self) -> None:
        pr = ProbeResult(
            provider="test",
            base_url="http://test",
            model="test",
            capabilities={},
            errors=["Connection refused"],
        )
        assert "Connection refused" in pr.summary()


class TestLLMMessage:
    def test_minimal_message(self) -> None:
        msg = LLMMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.tool_calls is None

    def test_tool_message(self) -> None:
        msg = LLMMessage(role="tool", content="result", tool_call_id="call_1")
        assert msg.tool_call_id == "call_1"


class TestLLMResponse:
    def test_defaults(self) -> None:
        resp = LLMResponse()
        assert resp.content is None
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"
        assert resp.usage == {}
