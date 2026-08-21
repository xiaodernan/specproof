"""Unit tests for agent.policy_dsl — fail-closed loading and pure evaluation.

No network, no external services: rule construction, YAML/JSON loading,
fail-closed validation, scope/severity/family/expiry matching, decision
ordering and digest stability are plain function calls (tmp_path only for
the file-loading cases).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

from agent.policy_dsl import (
    DSL_SCHEMA_VERSION,
    PolicyDecision,
    PolicyEvaluationError,
    PolicyLoadError,
    PolicyRule,
    PolicySet,
    PolicyValidationError,
    evaluate_policy,
    policy_digest,
)

NOW = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)

#: Pinned digest of the sample policy used in the stability test below.
#: Changing rule semantics must never change a digest silently — if this
#: pin breaks, the canonical document form changed and the change must be
#: deliberate.
PINNED_DIGEST = "d66c5a7af0335f8a9d1bd0249fa1cc4066170b1c21e8c5a80253f49e1ca3fc3a"


def _rule(**overrides: Any) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "id": "approve-auth-paths",
        "scope": "agent/**",
        "action": "require_approval",
        "reason": "auth paths need human approval",
    }
    rule.update(overrides)
    return rule


def _policy(rules: list[dict[str, Any]], version: str = "policy-v1") -> PolicySet:
    return PolicySet.from_dict({"version": version, "rules": rules})


def _change(**overrides: Any) -> dict[str, Any]:
    change: dict[str, Any] = {
        "paths": ["agent/graph.py"],
        "contract_family": "auth",
        "severity": "BLOCKER",
        "finding_id": "FIND-AUTH-01",
    }
    change.update(overrides)
    return change


def _decisions(
    policy: PolicySet, change: dict[str, Any], *, now: datetime | None = None
) -> list[PolicyDecision]:
    return evaluate_policy(policy, change, now=now)


# ── Fail-closed loading ─────────────────────────────────────────────────


def test_unknown_action_fails_closed() -> None:
    with pytest.raises(PolicyValidationError, match="unknown action"):
        _policy([_rule(action="auto_approve")])


def test_unknown_scope_fails_closed() -> None:
    with pytest.raises(PolicyValidationError, match="unknown scope"):
        _policy([_rule(scope="repository")])
    with pytest.raises(PolicyValidationError, match="unknown scope"):
        _policy([_rule(scope="everywhere")])


def test_unknown_rule_field_fails_closed() -> None:
    rule = _rule()
    rule["actions"] = "require_approval"
    with pytest.raises(PolicyValidationError, match="unknown field"):
        _policy([rule])


def test_unknown_top_level_field_fails_closed() -> None:
    raw: dict[str, Any] = {"version": "policy-v1", "rules": [_rule()], "owner": "alice"}
    with pytest.raises(PolicyValidationError, match="unknown field"):
        PolicySet.from_dict(raw)


def test_unknown_severity_fails_closed() -> None:
    with pytest.raises(PolicyValidationError, match="unknown severity"):
        _policy([_rule(severity_filter=["CATASTROPHIC"])])


def test_missing_required_field_fails_closed() -> None:
    rule = _rule()
    del rule["reason"]
    with pytest.raises(PolicyValidationError, match="missing required"):
        _policy([rule])


def test_duplicate_rule_id_fails_closed() -> None:
    with pytest.raises(PolicyValidationError, match="duplicate rule id"):
        _policy([_rule(), _rule(id="approve-auth-paths")])


def test_empty_rules_fails_closed() -> None:
    with pytest.raises(PolicyValidationError, match="non-empty list"):
        _policy([])


def test_malformed_expires_at_fails_closed() -> None:
    with pytest.raises(PolicyValidationError, match="expires_at"):
        _policy([_rule(expires_at="not-a-date")])


def test_non_list_severity_filter_fails_closed() -> None:
    with pytest.raises(PolicyValidationError, match="severity_filter"):
        _policy([_rule(severity_filter="BLOCKER")])


def test_direct_rule_construction_fails_closed() -> None:
    with pytest.raises(PolicyValidationError, match="action"):
        PolicyRule(id="x", scope="repo", action="auto_approve", reason="r")
    with pytest.raises(PolicyValidationError, match="scope"):
        PolicyRule(id="x", scope="repository", action="require_approval", reason="r")
    with pytest.raises(PolicyValidationError, match="bracket"):
        PolicyRule(id="x", scope="agent/[", action="require_approval", reason="r")
    with pytest.raises(PolicyValidationError, match="relative"):
        PolicyRule(id="x", scope="/agent/**", action="require_approval", reason="r")


def test_dsl_schema_version_is_pinned() -> None:
    assert DSL_SCHEMA_VERSION == "policy-dsl-v1"


# ── Scope matching ──────────────────────────────────────────────────────


def test_require_approval_matches_path_glob() -> None:
    policy = _policy([_rule()])
    decisions = _decisions(policy, _change(paths=["agent/graph.py"]))
    assert len(decisions) == 1
    assert decisions[0].action == "require_approval"
    assert decisions[0].matched_path == "agent/graph.py"
    assert _decisions(policy, _change(paths=["docs/README.md"])) == []


def test_star_stays_in_one_segment_double_star_crosses() -> None:
    star = _policy([_rule(id="star", scope="agent/*", action="forbid_change")])
    assert len(_decisions(star, _change(paths=["agent/graph.py"]))) == 1
    assert _decisions(star, _change(paths=["agent/nodes/prepare.py"])) == []
    deep = _policy([_rule(id="deep", scope="agent/**", action="forbid_change")])
    assert len(_decisions(deep, _change(paths=["agent/nodes/prepare.py"]))) == 1
    assert len(_decisions(deep, _change(paths=["agent"]))) == 1
    wild = _policy([_rule(id="py", scope="**/*.py", action="forbid_change")])
    assert len(_decisions(wild, _change(paths=["agent/nodes/prepare.py"]))) == 1
    assert _decisions(wild, _change(paths=["agent/nodes/README.md"])) == []


def test_literal_path_scope_matches_exactly() -> None:
    policy = _policy([_rule(id="exact", scope="agent/policy_dsl.py")])
    assert len(_decisions(policy, _change(paths=["agent/policy_dsl.py"]))) == 1
    assert _decisions(policy, _change(paths=["agent/waiver.py"])) == []


def test_windows_separators_are_normalized() -> None:
    policy = _policy([_rule(id="win", scope="agent/**")])
    assert len(_decisions(policy, _change(paths=["./agent\\nodes\\x.py"]))) == 1


def test_repo_and_tenant_scopes_match_every_change() -> None:
    policy = _policy([_rule(id="t", scope="tenant"), _rule(id="r", scope="repo")])
    decisions = _decisions(policy, _change(paths=[]))
    assert [d.rule_id for d in decisions] == ["r", "t"]


# ── Severity, family, expiry ────────────────────────────────────────────


def test_force_dynamic_evidence_on_severity() -> None:
    rule = _rule(
        id="dyn",
        action="force_dynamic_evidence",
        scope="repo",
        severity_filter=["BLOCKER", "MAJOR"],
    )
    policy = _policy([rule])
    assert _decisions(policy, _change(severity="BLOCKER"))[0].action == "force_dynamic_evidence"
    assert _decisions(policy, _change(severity="MAJOR"))[0].action == "force_dynamic_evidence"
    assert _decisions(policy, _change(severity="MINOR")) == []
    assert _decisions(policy, _change(severity="minor")) == []


def test_empty_severity_filter_matches_any_severity() -> None:
    policy = _policy([_rule(id="any", severity_filter=[])])
    assert len(_decisions(policy, _change(severity=None))) == 1
    assert len(_decisions(policy, _change(severity="NONE"))) == 1


def test_contract_family_filter() -> None:
    policy = _policy([_rule(id="fam", contract_family="auth")])
    assert len(_decisions(policy, _change(contract_family="auth"))) == 1
    assert _decisions(policy, _change(contract_family="billing")) == []
    assert _decisions(policy, _change(contract_family=None)) == []
    unfiltered = _policy([_rule(id="any")])
    assert len(_decisions(unfiltered, _change(contract_family="billing"))) == 1


def test_expired_rule_skipped_with_clock_applied_without() -> None:
    rule = _rule(
        id="temp",
        action="forbid_change",
        scope="repo",
        expires_at=(NOW - timedelta(days=1)).isoformat(),
    )
    policy = _policy([rule])
    assert _decisions(policy, _change(), now=NOW) == []
    assert [d.rule_id for d in _decisions(policy, _change())] == ["temp"]


def test_future_expiration_still_applies() -> None:
    rule = _rule(id="temp", scope="repo", expires_at=(NOW + timedelta(days=1)).isoformat())
    policy = _policy([rule])
    assert [d.action for d in _decisions(policy, _change(), now=NOW)] == ["require_approval"]


# ── Decisions and digest ────────────────────────────────────────────────


def test_decisions_carry_policy_version_and_digest() -> None:
    policy = _policy([_rule()])
    (decision,) = _decisions(policy, _change())
    assert decision.policy_version == "policy-v1"
    assert decision.policy_digest == policy.digest
    assert decision.rule_id == "approve-auth-paths"
    assert decision.action == "require_approval"
    assert decision.reason == "auth paths need human approval"
    assert decision.scope_kind == "path"
    assert decision.matched_path == "agent/graph.py"


def test_decision_order_is_specific_scope_first_then_id() -> None:
    policy = _policy(
        [
            _rule(id="t-rule", scope="tenant"),
            _rule(id="r-rule", scope="repo"),
            _rule(id="b-path", scope="agent/**"),
            _rule(id="a-path", scope="agent/**"),
        ]
    )
    decisions = _decisions(policy, _change())
    assert [d.rule_id for d in decisions] == ["a-path", "b-path", "r-rule", "t-rule"]


def test_digest_stable_across_key_order_rule_order_and_formats(tmp_path: Path) -> None:
    first = tmp_path / "policy-a.yaml"
    first.write_text(
        yaml.safe_dump(
            {
                "version": "policy-v1",
                "rules": [
                    {
                        "id": "a-rule",
                        "scope": "repo",
                        "action": "forbid_change",
                        "reason": "block everything",
                    },
                    {
                        "id": "b-rule",
                        "scope": "tenant",
                        "action": "require_security_review",
                        "reason": "review security",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    second = tmp_path / "policy-b.yaml"
    second.write_text(
        yaml.safe_dump(
            {
                "version": "policy-v1",
                "rules": [
                    {
                        "id": "b-rule",
                        "reason": "review security",
                        "action": "require_security_review",
                        "scope": "tenant",
                    },
                    {
                        "id": "a-rule",
                        "reason": "block everything",
                        "action": "forbid_change",
                        "scope": "repo",
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    third = tmp_path / "policy.json"
    third.write_text(
        json.dumps(
            {
                "version": "policy-v1",
                "rules": [
                    {
                        "id": "a-rule",
                        "scope": "repo",
                        "action": "forbid_change",
                        "reason": "block everything",
                    },
                    {
                        "id": "b-rule",
                        "scope": "tenant",
                        "action": "require_security_review",
                        "reason": "review security",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    first_set = PolicySet.load(first)
    second_set = PolicySet.load(second)
    third_set = PolicySet.load(third)
    assert first_set.digest == second_set.digest == third_set.digest
    assert first_set.digest == policy_digest(first_set.version, first_set.rules)
    assert first_set.digest == PINNED_DIGEST
    assert len(first_set.digest) == 64


def test_unsupported_extension_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "policy.txt"
    path.write_text("version: v1\nrules: []\n", encoding="utf-8")
    with pytest.raises(PolicyLoadError, match="extension"):
        PolicySet.load(path)


def test_malformed_json_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(PolicyLoadError, match="JSON"):
        PolicySet.load(path)


# ── Evaluation input ────────────────────────────────────────────────────


def test_evaluate_rejects_non_policy_and_non_mapping() -> None:
    policy = _policy([_rule()])
    with pytest.raises(PolicyEvaluationError):
        evaluate_policy("not a policy", _change())  # type: ignore[arg-type]
    with pytest.raises(PolicyEvaluationError):
        evaluate_policy(policy, "not a change")  # type: ignore[arg-type]
    with pytest.raises(PolicyEvaluationError):
        evaluate_policy(policy, _change(), now="yesterday")  # type: ignore[arg-type]
