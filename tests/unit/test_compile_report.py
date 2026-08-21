"""§14.1 unit tests — compile report for the compile_contracts node.

Deterministic, no network, no Docker. Covers:

- CompileReport / RejectedCandidate serialization roundtrip + tolerant
  from_dict for legacy or malformed stored projections;
- merge_reports semantics (counts add, lists concatenate, llm_used ORs);
- the deterministic node path fills the report with llm_used=False and
  leaves the contract output byte-identical to the pre-report node;
- an injected fake LLM marks llm_used=True and replaces the candidate
  set; schema-invalid LLM candidates land in rejected + schema_errors;
- LLM unavailability and LLM failures become degrade_reasons while the
  deterministic result is never discarded.
"""

from __future__ import annotations

import hashlib
import json
import types

import pytest

from agent.contracts.compile_report import (
    CompileReport,
    RejectedCandidate,
    merge_reports,
    requirement_digest,
)
from agent.contracts.records import checker_version_for
from agent.nodes.compile_contracts import (
    PARSER_RULE_VERSION,
    compile_contracts_node,
)

# Zero rule-pattern matches -> the LLM enrichment path is eligible (len < 2).
LLM_SPARSE_TEXT = "Users must be able to change their email address."

# Exactly one rule match (auth) -> deterministic list is non-empty but the
# LLM enrichment path is still eligible.
AUTH_ONLY_TEXT = "Unauthenticated requests must receive 401."

# Two rule matches -> the LLM is skipped entirely (historic policy).
TWO_FAMILY_TEXT = (
    "Unauthenticated requests must receive 401.\n"
    "Duplicate emails must be rejected with a unique constraint."
)


class FakeProvider:
    """Provider seam double: answers chat() with a canned content string."""

    def __init__(self, content: str, error: Exception | None = None) -> None:
        self.content = content
        self.error = error

    async def chat(self, messages: object = None, timeout: float = 0.0) -> object:
        if self.error is not None:
            raise self.error
        return types.SimpleNamespace(content=self.content)


def _patch_provider(monkeypatch: pytest.MonkeyPatch, provider: object) -> None:
    def factory() -> object:
        return provider

    monkeypatch.setattr("agent.nodes.compile_contracts._get_provider", factory)


# ── CompileReport dataclass + serialization ──────────────────────────────


def test_report_dict_roundtrip_and_json_ready():
    report = CompileReport(
        parser_rule_version="1.0.0",
        llm_used=True,
        candidate_count=5,
        accepted_count=3,
        rejected=[
            RejectedCandidate(reason="schema_invalid", candidate_summary="X-01 [sql]: bad"),
            RejectedCandidate(reason="replaced_by_llm", candidate_summary="AUTH-01 [http]: 401"),
        ],
        schema_errors=["X-01 [sql]: bad: missing or invalid requirement"],
        degrade_reasons=["LLM unavailable: LLM_API_KEY not configured"],
        requirement_digest="a" * 64,
        duration_ms=42,
    )
    assert CompileReport.from_dict(report.to_dict()) == report
    payload = json.dumps(report.to_dict())
    assert CompileReport.from_dict(json.loads(payload)) == report


def test_report_from_dict_tolerates_legacy_and_malformed_data():
    empty = CompileReport.from_dict({})
    assert empty == CompileReport(
        parser_rule_version="", llm_used=False, candidate_count=0, accepted_count=0
    )
    malformed = CompileReport.from_dict({
        "parser_rule_version": "2.0.0",
        "rejected": [{"reason": "x", "candidate_summary": "y"}, "not-an-object"],
        "schema_errors": ["e"],
        "duration_ms": "7",
    })
    assert malformed.parser_rule_version == "2.0.0"
    assert malformed.duration_ms == 7
    assert [r.reason for r in malformed.rejected] == ["x", "malformed_rejected_entry"]
    assert malformed.schema_errors == ["e"]


def test_merge_reports_combines_passes():
    first = CompileReport(
        parser_rule_version="1.0.0",
        llm_used=False,
        candidate_count=2,
        accepted_count=0,
        rejected=[RejectedCandidate(reason="replaced_by_llm", candidate_summary="A")],
        requirement_digest="d" * 64,
        duration_ms=10,
    )
    second = CompileReport(
        parser_rule_version="",
        llm_used=True,
        candidate_count=3,
        accepted_count=2,
        rejected=[RejectedCandidate(reason="schema_invalid", candidate_summary="B")],
        schema_errors=["B: missing or invalid id"],
        degrade_reasons=["LLM call failed: boom"],
        duration_ms=20,
    )
    merged = merge_reports([first, second])
    assert merged.parser_rule_version == "1.0.0"
    assert merged.llm_used is True
    assert merged.candidate_count == 5
    assert merged.accepted_count == 2
    assert [(r.reason, r.candidate_summary) for r in merged.rejected] == [
        ("replaced_by_llm", "A"),
        ("schema_invalid", "B"),
    ]
    assert merged.schema_errors == ["B: missing or invalid id"]
    assert merged.degrade_reasons == ["LLM call failed: boom"]
    assert merged.requirement_digest == "d" * 64
    assert merged.duration_ms == 30


def test_merge_reports_llm_used_is_or_not_and():
    off = CompileReport(
        parser_rule_version="1.0.0", llm_used=False,
        candidate_count=0, accepted_count=0,
    )
    on = CompileReport(
        parser_rule_version="1.0.0", llm_used=True,
        candidate_count=1, accepted_count=1,
    )
    assert merge_reports([off, off]).llm_used is False
    assert merge_reports([on, off]).llm_used is True


def test_merge_reports_requires_at_least_one_report():
    with pytest.raises(ValueError):
        merge_reports([])


def test_requirement_digest_is_stable_and_exact():
    assert requirement_digest("abc") == hashlib.sha256(b"abc").hexdigest()
    assert requirement_digest("abc") == requirement_digest("abc")
    assert requirement_digest("abc") != requirement_digest("abd")
    assert requirement_digest("") == hashlib.sha256(b"").hexdigest()


# ── Node: deterministic path ─────────────────────────────────────────────


def test_deterministic_node_fills_report_and_keeps_contracts_identical():
    state: dict[str, object] = {"requirement_text": TWO_FAMILY_TEXT, "use_llm": False}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    report = result["compile_report"]
    assert report["parser_rule_version"] == PARSER_RULE_VERSION
    assert report["llm_used"] is False
    assert report["candidate_count"] == 2
    assert report["accepted_count"] == 2
    assert report["rejected"] == []
    assert report["schema_errors"] == []
    assert report["degrade_reasons"] == []
    assert report["requirement_digest"] == requirement_digest(TWO_FAMILY_TEXT)
    assert isinstance(report["duration_ms"], int) and report["duration_ms"] >= 0
    # The contract output is byte-identical to the pre-report node: exact
    # ids, template behaviors, defaults and checker_version stamping.
    first_line = TWO_FAMILY_TEXT.strip().split("\n")[0][:120]
    assert result["contracts"] == [
        {
            "id": "AUTH-01",
            "requirement": first_line,
            "checker_type": "http",
            "expected_behavior": "Unauthenticated requests must receive 401 Unauthorized",
            "result": "UNVERIFIED",
            "evidence_ref": None,
            "approved": True,
            "version": 1,
            "checker_version": checker_version_for("http"),
        },
        {
            "id": "UNIQUE-01",
            "requirement": first_line,
            "checker_type": "sql",
            "expected_behavior": (
                "Duplicate email insertion must be rejected with "
                "constraint violation or application error"
            ),
            "result": "UNVERIFIED",
            "evidence_ref": None,
            "approved": True,
            "version": 1,
            "checker_version": checker_version_for("sql"),
        },
    ]


def test_empty_text_produces_empty_report():
    result = compile_contracts_node({"requirement_text": ""})  # type: ignore[arg-type]
    assert result["contracts"] == []
    report = result["compile_report"]
    assert report["candidate_count"] == 0
    assert report["accepted_count"] == 0
    assert report["requirement_digest"] == requirement_digest("")
    assert report["llm_used"] is False
    assert report["degrade_reasons"] == []


def test_registry_approved_path_reports_without_compiling():
    approved: list[dict[str, object]] = [{
        "id": "AUTH-01",
        "checker_type": "http",
        "requirement": "r",
        "expected_behavior": "e",
    }]
    state = {"requirement_text": "ignored", "approved_contracts": approved}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    report = result["compile_report"]
    assert report["candidate_count"] == 1
    assert report["accepted_count"] == 1
    assert report["llm_used"] is False
    assert report["degrade_reasons"] == []
    # W38 immutable-version backfills remain byte-identical.
    assert result["contracts"] == [{
        "id": "AUTH-01",
        "checker_type": "http",
        "requirement": "r",
        "expected_behavior": "e",
        "result": "UNVERIFIED",
        "evidence_ref": None,
        "approved": True,
        "version": 1,
        "checker_version": checker_version_for("http"),
    }]


# ── Node: injected fake LLM paths ────────────────────────────────────────


def test_fake_llm_path_marks_llm_used_and_replaces_candidates(monkeypatch):
    fake = FakeProvider(
        '[{"id": "LLM-01", "checker_type": "http", "requirement": "r", '
        '"expected_behavior": "e"}]'
    )
    _patch_provider(monkeypatch, fake)
    state: dict[str, object] = {"requirement_text": LLM_SPARSE_TEXT}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    report = result["compile_report"]
    assert report["llm_used"] is True
    assert report["candidate_count"] == 1
    assert report["accepted_count"] == 1
    assert report["rejected"] == []
    assert result["errors"] == []
    assert result["contracts"] == [{
        "id": "LLM-01",
        "checker_type": "http",
        "requirement": "r",
        "expected_behavior": "e",
        "result": "UNVERIFIED",
        "evidence_ref": None,
        "approved": True,
        "version": 1,
        "checker_version": checker_version_for("http"),
    }]


def test_llm_replacement_rejects_rule_candidates(monkeypatch):
    fake = FakeProvider(
        '[{"id": "LLM-01", "checker_type": "http", "requirement": "r", '
        '"expected_behavior": "e"}]'
    )
    _patch_provider(monkeypatch, fake)
    state: dict[str, object] = {"requirement_text": AUTH_ONLY_TEXT}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    report = result["compile_report"]
    assert report["llm_used"] is True
    assert report["candidate_count"] == 2  # 1 rule + 1 llm
    assert report["accepted_count"] == 1
    rejected = report["rejected"]
    assert [(r["reason"], "AUTH-01" in r["candidate_summary"]) for r in rejected] == [
        ("replaced_by_llm", True)
    ]
    assert [c["id"] for c in result["contracts"]] == ["LLM-01"]


def test_fake_llm_rejects_schema_invalid_candidates(monkeypatch):
    fake = FakeProvider(
        '[{"id": "LLM-01", "checker_type": "http", "requirement": "r", '
        '"expected_behavior": "e"}, '
        '{"id": "BROKEN-01", "checker_type": "sql"}, '
        '"not-an-object"]'
    )
    _patch_provider(monkeypatch, fake)
    state: dict[str, object] = {"requirement_text": LLM_SPARSE_TEXT}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    report = result["compile_report"]
    assert report["llm_used"] is True
    assert report["candidate_count"] == 3
    assert report["accepted_count"] == 1
    rejected = report["rejected"]
    assert [r["reason"] for r in rejected] == ["not_an_object", "schema_invalid"]
    assert "not-an-object" in rejected[0]["candidate_summary"]
    assert "BROKEN-01" in rejected[1]["candidate_summary"]
    assert any("missing or invalid requirement" in e for e in report["schema_errors"])
    assert any("missing or invalid expected_behavior" in e for e in report["schema_errors"])
    assert [c["id"] for c in result["contracts"]] == ["LLM-01"]


# ── Node: degradation paths ──────────────────────────────────────────────


def test_llm_unavailable_records_degrade_reason(monkeypatch):
    _patch_provider(monkeypatch, None)
    state: dict[str, object] = {"requirement_text": LLM_SPARSE_TEXT, "use_llm": True}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    report = result["compile_report"]
    assert report["llm_used"] is False
    assert report["degrade_reasons"] == ["LLM unavailable: LLM_API_KEY not configured"]
    assert report["candidate_count"] == 0
    assert report["accepted_count"] == 0
    assert result["contracts"] == []


def test_llm_call_failure_records_degrade_and_keeps_deterministic(monkeypatch):
    fake = FakeProvider("", error=RuntimeError("boom"))
    _patch_provider(monkeypatch, fake)
    state: dict[str, object] = {"requirement_text": AUTH_ONLY_TEXT}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    report = result["compile_report"]
    assert report["llm_used"] is False
    assert any("LLM call failed" in d for d in report["degrade_reasons"])
    assert len(result["contracts"]) == 1
    assert result["contracts"][0]["id"] == "AUTH-01"
    # Historic behavior: chat failures never polluted state["errors"].
    assert result["errors"] == []


def test_llm_empty_response_records_degrade_reason(monkeypatch):
    fake = FakeProvider("no json here")
    _patch_provider(monkeypatch, fake)
    state: dict[str, object] = {"requirement_text": LLM_SPARSE_TEXT}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    report = result["compile_report"]
    assert report["llm_used"] is False
    assert report["degrade_reasons"] == ["LLM response contained no JSON array"]
    assert result["contracts"] == []


# ── State channel ────────────────────────────────────────────────────────


def test_initial_state_declares_compile_report_channel():
    from agent.state import initial_state

    state = initial_state("/repo", "base", "head-v1", "spec.txt")
    assert state["compile_report"] == {}
