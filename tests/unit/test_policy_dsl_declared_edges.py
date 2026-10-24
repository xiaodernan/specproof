"""#432 — the policy DSL's declared-but-untested contracts, pinned.

`agent/policy_dsl.py` is a deterministic layer whose docstring declares a
contract: gitignore-style globbing (``* ? [...]`` stay in one segment, ``**``
spans segments, ``*`` matches dotfiles), fail-closed validation, a canonical
digest, and clock semantics where "naive means UTC" and a rule whose
``expires_at`` has been reached is inactive.

``test_policy_dsl.py`` already covers the happy paths, the main fail-closed
cases and digest stability. What it does **not** cover are the corners the
docstring promises but nothing asserts:

* the ``?`` and ``[...]`` metacharacters and dotfile matching;
* the expiry **boundary** (``now == expires_at`` must be inactive);
* clock normalisation (naive and non-UTC aware datetimes);
* input normalisation (``severity_filter`` case/whitespace, scope
  backslashes and a leading ``./``, trimmed ``id``/``reason``);
* the fail-closed branches no other test reaches (NUL byte, non-dict
  policy, missing/blank ``version``, ``rules`` not a list, a non-object
  rule entry, a ``severity_filter`` holding non-strings);
* digest **sensitivity** — stability is pinned, but so must be the fact
  that a different rule produces a different digest.

The module is unchanged by this file: these are behaviour pins, not fixes.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from agent.policy_dsl import (
    PolicyRule,
    PolicySet,
    PolicyValidationError,
    _parse_datetime,
    _path_matches,
    _scope_kind,
    evaluate_policy,
    policy_digest,
)


def _rule(**overrides: Any) -> dict[str, Any]:
    rule: dict[str, Any] = {
        "id": "r1",
        "scope": "repo",
        "action": "require_approval",
        "reason": "because",
    }
    rule.update(overrides)
    return rule


def _policy(rules: list[dict[str, Any]]) -> PolicySet:
    return PolicySet.from_dict({"version": "policy-v1", "rules": rules})


def _change(**overrides: Any) -> dict[str, Any]:
    change: dict[str, Any] = {"paths": ["agent/graph.py"], "severity": "BLOCKER"}
    change.update(overrides)
    return change


# ── Declared glob semantics ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        # '*' matches dotfiles — declared, and it matters: a policy scope of
        # "config/*" must see ".env".
        ("agent/.env", "agent/*", True),
        ("agent/nodes/.hidden.py", "agent/nodes/*", True),
        # '?' matches exactly one character, and only one.
        ("agent/x.py", "agent/?.py", True),
        ("agent/ab.py", "agent/?.py", False),
        # '[...]' character classes.
        ("agent/a.py", "agent/[ab].py", True),
        ("agent/b.py", "agent/[ab].py", True),
        ("agent/c.py", "agent/[ab].py", False),
        # glob metacharacters stay inside one segment.
        ("agent/nodes/x.py", "agent/*", False),
        ("agent/nodes/x.py", "agent/**", True),
    ],
)
def test_declared_glob_metacharacters(path: str, pattern: str, expected: bool) -> None:
    assert _path_matches(path, pattern) is expected


def test_scope_with_glob_magic_but_no_slash_is_a_path_scope() -> None:
    # A bare unknown word is rejected, but glob magic alone classifies as a
    # path pattern even without a '/'.
    assert _scope_kind("*.py") == "path"
    assert _scope_kind("agent?.py") == "path"
    with pytest.raises(PolicyValidationError, match="unknown scope"):
        _scope_kind("just-a-word")


# ── Clock semantics ─────────────────────────────────────────────────────


def test_expiry_boundary_now_equal_to_expires_at_is_inactive() -> None:
    expires = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    policy = _policy(
        [_rule(id="temp", scope="repo", expires_at=expires.isoformat())]
    )
    # exactly at the instant of expiry -> the rule is no longer active.
    assert evaluate_policy(policy, _change(), now=expires) == []
    # one second before -> still active.
    assert len(evaluate_policy(policy, _change(), now=expires - timedelta(seconds=1))) == 1


def test_naive_now_is_treated_as_utc() -> None:
    expires = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    policy = _policy([_rule(id="temp", scope="repo", expires_at=expires.isoformat())])
    naive_before = datetime(2026, 8, 20, 11, 59, 59)  # no tzinfo -> assumed UTC
    assert len(evaluate_policy(policy, _change(), now=naive_before)) == 1


def test_non_utc_aware_now_is_converted_before_comparison() -> None:
    expires = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    policy = _policy([_rule(id="temp", scope="repo", expires_at=expires.isoformat())])
    # 20:00 in UTC+8 is 12:00 UTC — the same instant, so still expired.
    same_instant = datetime(2026, 8, 20, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert evaluate_policy(policy, _change(), now=same_instant) == []
    earlier = datetime(2026, 8, 20, 19, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert len(evaluate_policy(policy, _change(), now=earlier)) == 1


# ── Construction normalisation ──────────────────────────────────────────


def test_rule_construction_normalises_severity_scope_and_trims_text() -> None:
    rule = PolicyRule(
        id="  spaced-id  ",
        scope=".\\agent\\nodes\\**",
        action="require_approval",
        reason="  padded reason  ",
        severity_filter=[" blocker ", "major"],
        contract_family="  auth  ",
    )
    assert rule.id == "spaced-id"
    assert rule.scope == "agent/nodes/**"
    assert rule.reason == "padded reason"
    assert rule.severity_filter == ("BLOCKER", "MAJOR")
    assert rule.contract_family == "auth"
    # the normalized scope actually matches through the same rule.
    policy = PolicySet(version="v", rules=(rule,), digest="d")
    matched = evaluate_policy(
        policy, _change(paths=["agent/nodes/x.py"], contract_family="auth")
    )
    assert len(matched) == 1
    # ...and the family filter still excludes a different family.
    other = evaluate_policy(
        policy, _change(paths=["agent/nodes/x.py"], contract_family="billing")
    )
    assert other == []


def test_rule_construction_treats_naive_expires_at_as_utc() -> None:
    rule = PolicyRule(
        id="naive",
        scope="repo",
        action="require_approval",
        reason="r",
        expires_at=datetime(2026, 8, 20, 12, 0, 0),  # naive
    )
    assert rule.expires_at is not None
    assert rule.expires_at.tzinfo is UTC
    assert rule.expires_at.utcoffset() == timedelta(0)


def test_rule_to_dict_renders_microsecond_expiry_in_canonical_form() -> None:
    stamp = datetime(2026, 8, 20, 12, 0, 0, 123456, tzinfo=UTC)
    rule = PolicyRule(id="micro", scope="repo", action="require_approval",
                      reason="r", expires_at=stamp)
    assert rule.to_dict()["expires_at"] == "2026-08-20T12:00:00.123456Z"
    # and the canonical rendering feeds the digest deterministically.
    whole = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    other = PolicyRule(id="micro", scope="repo", action="require_approval",
                       reason="r", expires_at=whole)
    assert rule.to_dict()["expires_at"] != other.to_dict()["expires_at"]


def test_rule_construction_rejects_blank_text_fields() -> None:
    for kwargs in (
        {"id": "   ", "scope": "repo"},
        {"id": "ok", "scope": "   "},
        {"id": "ok", "scope": "repo", "reason": "  "},
    ):
        base = {"id": "ok", "scope": "repo", "action": "require_approval", "reason": "r"}
        base.update(kwargs)
        with pytest.raises(PolicyValidationError):
            PolicyRule(**base)  # type: ignore[arg-type]


def test_rule_construction_rejects_blank_contract_family_and_nul_scope() -> None:
    with pytest.raises(PolicyValidationError, match="contract_family"):
        PolicyRule(id="x", scope="repo", action="require_approval",
                   reason="r", contract_family="   ")
    with pytest.raises(PolicyValidationError, match="NUL"):
        PolicyRule(id="x", scope="agent/\x00bad", action="require_approval", reason="r")


# ── Fail-closed branches nothing else reaches ───────────────────────────


def test_parse_datetime_rejects_non_string() -> None:
    with pytest.raises(PolicyValidationError, match="ISO-8601 string"):
        _parse_datetime(12345, where="rule[0]")
    with pytest.raises(PolicyValidationError, match="ISO-8601 string"):
        _parse_datetime(None, where="rule[0]")


def test_from_dict_rejects_non_object_and_empty_object() -> None:
    for raw in ([], "nope", 42, {}):
        with pytest.raises(PolicyValidationError, match="non-empty object"):
            PolicySet.from_dict(raw)  # type: ignore[arg-type]


def test_from_dict_rejects_missing_or_blank_version() -> None:
    with pytest.raises(PolicyValidationError, match="version"):
        PolicySet.from_dict({"rules": [_rule()]})
    with pytest.raises(PolicyValidationError, match="version"):
        PolicySet.from_dict({"version": "   ", "rules": [_rule()]})
    with pytest.raises(PolicyValidationError, match="version"):
        PolicySet.from_dict({"version": 7, "rules": [_rule()]})


def test_from_dict_rejects_non_list_and_empty_rules() -> None:
    with pytest.raises(PolicyValidationError, match="rules"):
        PolicySet.from_dict({"version": "v", "rules": {"a": 1}})
    with pytest.raises(PolicyValidationError, match="rules"):
        PolicySet.from_dict({"version": "v", "rules": []})


def test_parse_rule_rejects_non_object_entry_and_non_string_severities() -> None:
    with pytest.raises(PolicyValidationError, match="expected an object"):
        PolicySet.from_dict({"version": "v", "rules": ["not a rule"]})
    with pytest.raises(PolicyValidationError, match="list of strings"):
        PolicySet.from_dict(
            {"version": "v", "rules": [_rule(severity_filter=["BLOCKER", 3])]}
        )


# ── Digest sensitivity ──────────────────────────────────────────────────


def test_digest_changes_when_a_rule_changes() -> None:
    base = _policy([_rule(id="a", scope="repo")])
    changed_action = _policy([_rule(id="a", scope="repo", action="forbid_change")])
    changed_reason = _policy([_rule(id="a", scope="repo", reason="other")])
    assert base.digest != changed_action.digest
    assert base.digest != changed_reason.digest
    # and equals the pure function the module documents as the digest source.
    assert base.digest == policy_digest(base.version, base.rules)


# ── Change input normalisation ──────────────────────────────────────────


def test_paths_given_as_a_bare_string_silently_matches_no_path_rule() -> None:
    # Pinned as a known behaviour, not an endorsement: `paths` is documented
    # as a list. A bare string yields no path rules matched (a path-scoped
    # forbid_change would silently not fire) while repo/tenant rules still do.
    policy = _policy(
        [
            _rule(id="p", scope="agent/**", action="forbid_change"),
            _rule(id="r", scope="repo", action="require_approval"),
        ]
    )
    decisions = evaluate_policy(policy, _change(paths="agent/graph.py"))
    assert [d.rule_id for d in decisions] == ["r"]
    # the same change as a list matches both.
    both = evaluate_policy(policy, _change(paths=["agent/graph.py"]))
    assert [d.rule_id for d in both] == ["p", "r"]


def test_paths_drop_non_strings_and_root_only_entries() -> None:
    policy = _policy([_rule(id="p", scope="agent/**", action="forbid_change")])
    decisions = evaluate_policy(policy, _change(paths=["/", "./", 42, None, "agent/graph.py"]))
    assert len(decisions) == 1
    assert decisions[0].matched_path == "agent/graph.py"


def test_severity_and_family_non_string_values_normalize_to_none() -> None:
    filtered = _policy([_rule(id="s", scope="repo", severity_filter=["BLOCKER"])])
    # a non-string severity cannot match a filter -> the rule does not fire.
    assert evaluate_policy(filtered, _change(severity=42)) == []
    # an unfiltered rule still fires regardless of the severity's type.
    unfiltered = _policy([_rule(id="any", scope="repo")])
    assert len(evaluate_policy(unfiltered, _change(severity=42))) == 1
    # a non-string contract family never equals a set family filter.
    fam = _policy([_rule(id="f", scope="repo", contract_family="auth")])
    assert evaluate_policy(fam, _change(contract_family=42)) == []
