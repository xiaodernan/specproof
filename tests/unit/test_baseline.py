"""Unit tests — specproof baseline (diff-only reviewer comparison)."""

import asyncio
import subprocess
from pathlib import Path

import httpx
from click.testing import CliRunner

from cli.specproof.commands.baseline import (
    _extract_findings,
    _get_provider,
    baseline_cmd,
    capture_diff,
    deterministic_baseline,
    judge_case,
    llm_baseline,
    preflight_probe,
    render_report,
    summarize,
)
from providers.base import LLMMessage, LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider


def test_deterministic_reader_detects_removed_preauthorize():
    diff = (
        "diff --git a/UserController.java b/UserController.java\n"
        "-    @PreAuthorize(\"isAuthenticated()\")\n"
        "     public void changeEmail() {}\n"
    )
    findings = deterministic_baseline(diff)
    assert len(findings) == 1
    assert findings[0]["contract_id"] == "AUTH-01"
    assert findings[0]["severity"] == "BLOCKER"


def test_reader_skips_modified_guard():
    # Condition inverted (removed + near-identical added) is a MODIFICATION:
    # a conservative static reader cannot call it a regression.
    diff = (
        "diff --git a/UserService.java b/UserService.java\n"
        "-        if (userRepository.existsByEmail(newEmail)) {\n"
        "+        if (!userRepository.existsByEmail(newEmail)) {\n"
    )
    assert deterministic_baseline(diff) == []


def test_reader_flags_deleted_uniqueness_guard():
    diff = (
        "diff --git a/UserService.java b/UserService.java\n"
        "-        if (userRepository.existsByEmail(newEmail)) {\n"
        "-            throw new RuntimeException(\"duplicate\");\n"
        "-        }\n"
    )
    findings = deterministic_baseline(diff)
    ids = {f["contract_id"] for f in findings}
    assert "UNIQUE-01" in ids


def test_reader_flags_added_publish_call():
    diff = (
        "diff --git a/UserService.java b/UserService.java\n"
        "+        rabbitTemplate.convertAndSend(\"x\", \"email.changed\", event);\n"
    )
    findings = deterministic_baseline(diff)
    assert any(f["contract_id"] == "EVENT_ONCE-01" for f in findings)


def test_reader_ignores_added_comments():
    diff = (
        "diff --git a/UserController.java b/UserController.java\n"
        "+/** documentation only */\n"
        "+        // another comment\n"
    )
    assert deterministic_baseline(diff) == []


def test_judge_positive_pass():
    gt = {
        "should_detect": True,
        "expected_contract": "AUTH-01",
        "expected_evidence_type": "differential_test",
    }
    row = judge_case(
        "case-x",
        gt,
        [{
            "contract_id": "AUTH-01",
            "severity": "BLOCKER",
            "evidence_type": "java_source_diff",
        }],
    )
    assert row["verdict"] == "PASS"
    assert row["detected"] is True


def test_judge_miss():
    gt = {
        "should_detect": True,
        "expected_contract": "AUTH-01",
        "expected_evidence_type": "differential_test",
    }
    row = judge_case("case-x", gt, [])
    assert row["verdict"] == "MISS"
    assert row["detected"] is False


def test_judge_negative_any_finding_is_false_positive():
    gt = {"should_detect": False, "expected_contract": None}
    row = judge_case(
        "case-x",
        gt,
        [{"contract_id": "EVENT_ONCE-01", "severity": "MAJOR"}],
    )
    assert row["verdict"] == "FALSE_POSITIVE"
    assert row["false_positive"] is True


def test_judge_partial_when_below_min_findings():
    gt = {
        "should_detect": True,
        "expected_contract": "AUTH-01",
        "expected_min_findings": 2,
    }
    row = judge_case(
        "case-x",
        gt,
        [{"contract_id": "AUTH-01", "severity": "BLOCKER"}],
    )
    assert row["verdict"] == "PARTIAL"
    assert row["detected"] is True


def test_summarize_aggregates():
    rows = [
        {"should_detect": True, "detected": True, "false_positive": False},
        {"should_detect": True, "detected": False, "false_positive": False},
        {"should_detect": False, "detected": False, "false_positive": False},
        {"should_detect": False, "detected": False, "false_positive": True},
    ]
    summary = summarize(rows)
    assert summary["detected"] == 1
    assert summary["recall"] == 50.0
    assert summary["precision"] == 50.0
    assert summary["false_positives"] == 1


def test_render_report_gate_math():
    rows: list[dict] = []
    baseline_summary = {"total_cases": 8, "recall": 62.5, "precision": 80.0}
    specproof = {
        "recall": 100.0,
        "precision": 100.0,
    }
    report = render_report(rows, baseline_summary, specproof, "deterministic")
    assert "+37.5pp" in report
    assert "**PASS**" in report
    failing = render_report(
        rows, {"total_cases": 8, "recall": 95.0, "precision": 90.0},
        specproof, "deterministic",
    )
    assert "**FAIL**" in failing


def test_render_report_without_specproof_results():
    rows: list[dict] = []
    report = render_report(
        rows, {"total_cases": 0, "recall": 0.0, "precision": 0.0},
        None, "deterministic",
    )
    assert "SpecProof 结果文件缺失" in report


def test_capture_diff_roundtrip(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q"], cwd=repo, check=True, timeout=60,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=repo, check=True, timeout=60,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"], cwd=repo, check=True, timeout=60,
    )
    (repo / "A.java").write_text("int a = 1;\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, timeout=60)
    subprocess.run(
        ["git", "commit", "-qm", "base"], cwd=repo, check=True, timeout=60,
    )
    subprocess.run(
        ["git", "checkout", "-qb", "head"], cwd=repo, check=True, timeout=60,
    )
    (repo / "A.java").write_text("int a = 2;\n", encoding="utf-8")
    subprocess.run(
        ["git", "commit", "-qam", "head"], cwd=repo, check=True, timeout=60,
    )
    diff = capture_diff(str(repo), "master", "head")
    assert "int a = 2" in diff
    assert "int a = 1" in diff


# ═══════════════════════════════════════════════════════════════
# LLM baseline mode (--mode llm)
# ═══════════════════════════════════════════════════════════════

class StubBaselineProvider:
    """Captures chat() input and returns a canned LLMResponse."""

    def __init__(self, response: LLMResponse | None = None) -> None:
        self.response = response or LLMResponse()
        self.messages: list[list[LLMMessage]] = []
        self.tools: list[dict] | None = None
        self.response_format: dict | None = None

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
        thinking: bool = False,
        timeout: float = 180.0,
    ) -> LLMResponse:
        self.messages.append(messages)
        self.tools = tools
        self.response_format = response_format
        return self.response


def _tool_call_finding() -> dict:
    return {
        "id": "call-1",
        "type": "function",
        "function": {
            "name": "report_findings",
            "arguments": (
                '{"findings": [{"contract_id": "AUTH-01", "severity": '
                '"blocker", "confidence": 0.9, "evidence": "@PreAuthorize '
                'removed in Head"}]}'
            ),
        },
    }


async def test_llm_baseline_parses_tool_calls():
    provider = StubBaselineProvider(
        response=LLMResponse(content=None, tool_calls=[_tool_call_finding()])
    )
    findings, note = await llm_baseline("diff", "spec", provider)
    assert note == ""
    assert len(findings) == 1
    assert findings[0]["contract_id"] == "AUTH-01"
    assert findings[0]["severity"] == "BLOCKER"
    assert findings[0]["confidence"] == 0.9
    assert "PreAuthorize" in findings[0]["evidence"]
    # Tools + json_object envelope are handed to the provider so its
    # degradation logic (JSON Action Envelope) can kick in.
    assert provider.tools is not None
    assert provider.response_format == {"type": "json_object"}


async def test_llm_baseline_parses_action_envelope():
    content = (
        '{"action": "report_findings", "params": {"findings": ['
        '{"contract_id": "UNIQUE-01", "severity": "MAJOR", '
        '"confidence": 0.7, "evidence": "guard removed"}]}}'
    )
    provider = StubBaselineProvider(response=LLMResponse(content=content))
    findings, note = await llm_baseline("diff", "spec", provider)
    assert note == ""
    assert len(findings) == 1
    assert findings[0]["contract_id"] == "UNIQUE-01"
    assert findings[0]["severity"] == "MAJOR"


async def test_llm_baseline_parses_plain_findings_json():
    content = '{"findings": [{"contract_id": "TRANSACTION-01", "severity": "MAJOR"}]}'
    provider = StubBaselineProvider(response=LLMResponse(content=content))
    findings, note = await llm_baseline("diff", "spec", provider)
    assert note == ""
    assert len(findings) == 1
    assert findings[0]["contract_id"] == "TRANSACTION-01"


async def test_llm_baseline_empty_findings_is_clean_parse():
    content = '{"findings": []}'
    provider = StubBaselineProvider(response=LLMResponse(content=content))
    findings, note = await llm_baseline("diff", "spec", provider)
    assert findings == []
    assert note == ""


async def test_llm_baseline_unparseable_reply_returns_note_not_error():
    provider = StubBaselineProvider(
        response=LLMResponse(content="sorry, I cannot review this diff")
    )
    findings, note = await llm_baseline("diff", "spec", provider)
    assert findings == []
    assert "unparseable" in note


async def test_llm_baseline_redacts_secrets_before_sending():
    # Concatenated on purpose: the security scanners (tests/security/)
    # forbid a full "sk-" + long-key pattern inline, even in test fixtures.
    secret = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    provider = StubBaselineProvider(
        response=LLMResponse(content='{"findings": []}')
    )
    findings, _note = await llm_baseline(
        "diff --git a/A.java b/A.java\n+" + secret + "\n", "spec", provider
    )
    assert findings == []
    prompt = provider.messages[0][0].content or ""
    assert secret not in prompt
    assert "[REDACTED:llm_api_key]" in prompt


async def test_llm_prompt_is_deterministic_per_case():
    provider = StubBaselineProvider(
        response=LLMResponse(content='{"findings": []}')
    )
    diff = "diff --git a/A.java b/A.java\n-@PreAuthorize\n"
    await llm_baseline(diff, "spec: auth required", provider)
    await llm_baseline(diff, "spec: auth required", provider)
    first = provider.messages[0][0].content
    second = provider.messages[1][0].content
    assert first == second
    assert "auth required" in first
    assert "@PreAuthorize" in first


def test_extract_findings_normalizes_and_ignores_non_dicts():
    content = (
        '{"findings": [{"contract_id": "AUTH-01", "severity": "major", '
        '"confidence": "high", "evidence": "x"}, "garbage", '
        '{"id": "B-1", "severity": "minor"}]}'
    )
    findings, note = _extract_findings(content, [])
    assert note == ""
    assert len(findings) == 2
    assert findings[0]["contract_id"] == "AUTH-01"
    assert findings[0]["severity"] == "MAJOR"
    assert "confidence" not in findings[0]  # non-numeric confidence dropped
    assert findings[1]["contract_id"] == "B-1"
    assert findings[1]["severity"] == "MINOR"


def test_get_provider_without_key_is_none(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert _get_provider() is None


def test_get_provider_with_placeholder_key_is_none(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "replace_me")
    assert _get_provider() is None


def test_get_provider_with_key_builds_provider(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fake-" + "key-123456")
    provider = _get_provider()
    assert provider is not None


def test_preflight_probe_gateway_unreachable_returns_reason(monkeypatch):
    """Gateway 401: the probe must report failure honestly, never pretend.

    Mock strategy: the project's HTTP layer is httpx (CapabilityProbe),
    which the responses library (0.26.2) does not intercept in this
    environment — so the AsyncClient transport is stubbed directly; no
    real network is ever touched.
    """

    class _UnauthorizedAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def get(self, url: str, headers: dict | None = None):
            return httpx.Response(401, request=httpx.Request("GET", url))

        async def post(self, url: str, headers: dict | None = None, json=None):
            return httpx.Response(401, request=httpx.Request("POST", url))

    import providers.capability_probe as capability_probe

    # W191 (§14 统一网络客户端) 后 probe 经 providers.net.make_async_client
    # 构造 httpx 客户端 — 桩该构造点等效于旧版桩 AsyncClient, 网络永不触达。
    monkeypatch.setattr(
        capability_probe, "make_async_client",
        lambda timeout=None: _UnauthorizedAsyncClient(),
    )
    provider = OpenAICompatibleProvider(
        base_url="http://llm.test",
        api_key="probe-" + "test-key",
        model="probe-model",
        probe_on_init=False,
    )
    reason = asyncio.run(preflight_probe(provider))
    assert "gateway probe failed" in reason
    assert "401" in reason


def test_cli_mode_llm_without_key_exits_nonzero(tmp_path, monkeypatch):
    cases = tmp_path / "cases"
    (cases / "case-01").mkdir(parents=True)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    runner = CliRunner()
    result = runner.invoke(
        baseline_cmd,
        ["--cases", str(cases), "--repo", str(tmp_path), "--mode", "llm"],
    )
    assert result.exit_code == 2
    assert "LLM baseline unavailable" in result.output


def test_cli_no_llm_conflicts_with_mode_llm():
    runner = CliRunner()
    result = runner.invoke(
        baseline_cmd,
        ["--cases", ".", "--repo", ".", "--no-llm", "--mode", "llm"],
    )
    assert result.exit_code == 2
    assert "conflicts" in result.output


def test_cli_help_lists_mode_option():
    runner = CliRunner()
    result = runner.invoke(baseline_cmd, ["--help"])
    assert result.exit_code == 0
    assert "--mode" in result.output
    assert "diff-reader" in result.output
    assert "--llm" in result.output


def test_summarize_includes_f1():
    rows = [
        {"should_detect": True, "detected": True, "false_positive": False},
        {"should_detect": True, "detected": False, "false_positive": False},
        {"should_detect": False, "detected": False, "false_positive": False},
        {"should_detect": False, "detected": False, "false_positive": True},
    ]
    summary = summarize(rows)
    assert summary["f1"] == 50.0


def test_render_report_includes_f1_row_when_sidecar_has_f1():
    rows: list[dict] = []
    baseline_summary = {"total_cases": 8, "recall": 62.5, "precision": 80.0, "f1": 70.2}
    specproof = {"recall": 100.0, "precision": 100.0, "f1": 100.0}
    report = render_report(rows, baseline_summary, specproof, "deterministic")
    assert "| F1 | 100.0% | 70.2% | +29.8pp |" in report


def test_render_report_marks_llm_parse_failures():
    rows: list[dict] = []
    report = render_report(
        rows, {"total_cases": 1, "recall": 0.0, "precision": 100.0, "f1": 0.0},
        None, "LLM (diff + requirement)", parse_failures=1,
    )
    assert "LLM 解析失败案例: 1" in report
