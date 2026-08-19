"""Organizational policy-as-code DSL (工业化指南 §6.6, 阶段 3 第一片).

First slice of the policy center: a declarative policy file (YAML or JSON)
whose rules decide what a change must go through — human approval, dynamic
evidence, a security review, a hard change block, or an allowed finding
waiver. This module is the deterministic layer:

* ``PolicyRule`` — the frozen rule record. Construction validates the
  vocabulary and fails closed: an unknown action/scope, an unknown
  severity, a malformed expiration or an extra key raises
  ``PolicyValidationError`` instead of being silently ignored.
* ``PolicySet`` — the loaded, validated policy: ``version`` +
  ``digest`` + rules, built from YAML/JSON via ``PolicySet.load``.
* ``evaluate_policy`` — the pure matcher: the same policy and change
  always produce the same decision list (no I/O, no randomness, no hidden
  clock).

Fail-closed semantics (策略判断要成为证据的一部分):

* ``action`` must be one of ``ACTIONS``; ``scope`` must be
  ``repo``, ``tenant``, or a path pattern (a string containing
  ``/`` or glob metacharacters ``* ? [``). A bare unknown word is
  rejected rather than treated as a never-matching pattern.
* path patterns are relative to the repository root, use ``/``
  separators, and follow gitignore segment semantics: ``* ? [...]``
  stay inside one segment, ``**`` spans any number of segments,
  matching is case-sensitive and ``*`` also matches dotfiles.
* every decision carries ``policy_version`` and ``policy_digest``
  so the decision list can be embedded into evidence and replayed later.
* ``policy_digest`` hashes the DSL schema, version and all rules in
  canonical form (fixed field order, rules sorted by id), so YAML key
  order, rule order and YAML-vs-JSON formatting never change the digest.

Clock contract: ``evaluate_policy`` takes an optional ``now``. With
a clock, rules whose ``expires_at`` has passed are skipped; without
one (``now=None``) every loaded rule is applied as written. Naive
datetimes, in the policy file or in the clock, are treated as UTC.

Decision ordering is deterministic: path rules first (most specific
scope), then repo, then tenant; rules sharing a scope are ordered by id.
The decision list itself resolves nothing — consumers combine the actions
(e.g. any ``forbid_change`` blocks the merge).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Literal

import yaml

# ── Vocabulary ──────────────────────────────────────────────────────────

#: The five actions a rule can demand. Unknown actions fail closed.
ACTIONS: frozenset[str] = frozenset(
    {
        "require_approval",
        "forbid_change",
        "force_dynamic_evidence",
        "require_security_review",
        "allow_waiver",
    }
)

#: Canonical severity vocabulary (BLOCKER/MAJOR/MINOR from the review
#: court, INFORMATIONAL from the policy layer, NONE from golden-case
#: ground truth). Severity filters are validated against this set.
SEVERITIES: frozenset[str] = frozenset(
    {"BLOCKER", "MAJOR", "MINOR", "INFORMATIONAL", "NONE"}
)

SCOPE_REPO = "repo"
SCOPE_TENANT = "tenant"
ScopeKind = Literal["repo", "tenant", "path"]

#: Version of this DSL schema, embedded in the policy digest so a digest
#: can never be replayed against a different schema.
DSL_SCHEMA_VERSION = "policy-dsl-v1"

_GLOB_MAGIC = frozenset("*?[")
_POLICY_FIELDS: frozenset[str] = frozenset({"version", "rules"})
_RULE_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "scope",
        "action",
        "severity_filter",
        "contract_family",
        "expires_at",
        "reason",
    }
)
_SCOPE_ORDER: dict[str, int] = {"path": 0, "repo": 1, "tenant": 2}


# ── Errors ──────────────────────────────────────────────────────────────


class PolicyError(ValueError):
    """Base error raised by the policy DSL."""


class PolicyValidationError(PolicyError):
    """Policy content is invalid; loading fails closed."""


class PolicyLoadError(PolicyError):
    """Policy file is missing, unreadable or in an unsupported format."""


class PolicyEvaluationError(PolicyError):
    """Evaluation input is not a policy/change this module can judge."""


# ── Time helpers ────────────────────────────────────────────────────────


def _as_utc(value: datetime) -> datetime:
    """Normalize a datetime to aware UTC; naive values are assumed UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    """Canonical ISO-8601 UTC rendering used by serialization and digests."""
    utc = _as_utc(value)
    if utc.microsecond:
        return utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_datetime(value: Any, *, where: str) -> datetime:
    """Parse an ISO-8601 expiration, normalizing to aware UTC."""
    if not isinstance(value, str):
        raise PolicyValidationError(f"{where}: 'expires_at' must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise PolicyValidationError(f"{where}: invalid 'expires_at' {value!r}: {exc}") from exc
    return _as_utc(parsed)


# ── Scope classification and path matching ──────────────────────────────


def _scope_kind(scope: str) -> ScopeKind:
    """Classify one scope value; unknown scopes raise (fail closed)."""
    if scope == SCOPE_REPO:
        return "repo"
    if scope == SCOPE_TENANT:
        return "tenant"
    if "/" in scope or any(char in scope for char in _GLOB_MAGIC):
        return "path"
    raise PolicyValidationError(
        f"unknown scope {scope!r}: expected 'repo', 'tenant' or a path "
        "pattern containing '/' or glob metacharacters (* ? [)"
    )


def _validate_path_pattern(pattern: str) -> None:
    """Reject path patterns this module cannot match deterministically."""
    if pattern.startswith("/"):
        raise PolicyValidationError(
            f"path scope {pattern!r} must be relative to the repository root "
            "(no leading '/')"
        )
    if "\x00" in pattern:
        raise PolicyValidationError(f"path scope {pattern!r} contains a NUL byte")
    if pattern.count("[") != pattern.count("]"):
        raise PolicyValidationError(
            f"path scope {pattern!r} has unbalanced '['/']' brackets"
        )


def _normalize_path(value: str) -> str:
    """One path in canonical repo-relative form ('/' separators, no './')."""
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _match_parts(path_parts: Sequence[str], pattern_parts: Sequence[str]) -> bool:
    """Segment-wise glob match; '**' spans any number of segments."""
    if not pattern_parts:
        return not path_parts
    head, rest = pattern_parts[0], pattern_parts[1:]
    if head == "**":
        return any(
            _match_parts(path_parts[skip:], rest) for skip in range(len(path_parts) + 1)
        )
    if not path_parts or not fnmatchcase(path_parts[0], head):
        return False
    return _match_parts(path_parts[1:], rest)


def _path_matches(path: str, pattern: str) -> bool:
    """Whether one normalized path matches one validated path scope."""
    pattern_parts = [part for part in pattern.split("/") if part]
    path_parts = [part for part in path.split("/") if part]
    return _match_parts(path_parts, pattern_parts)


# ── Policy records ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PolicyRule:
    """One declarative rule; construction fails closed on bad vocabulary."""

    id: str
    scope: str
    action: str
    reason: str
    severity_filter: tuple[str, ...] = ()
    contract_family: str | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise PolicyValidationError("rule 'id' must be a non-empty string")
        object.__setattr__(self, "id", self.id.strip())

        if not self.scope.strip():
            raise PolicyValidationError(f"rule {self.id!r}: 'scope' must be a non-empty string")
        scope = self.scope.strip().replace("\\", "/")
        while scope.startswith("./"):
            scope = scope[2:]
        kind = _scope_kind(scope)
        if kind == "path":
            _validate_path_pattern(scope)
        object.__setattr__(self, "scope", scope)

        if self.action not in ACTIONS:
            raise PolicyValidationError(
                f"rule {self.id!r}: unknown action {self.action!r}; "
                f"expected one of {sorted(ACTIONS)}"
            )

        severities = tuple(severity.strip().upper() for severity in self.severity_filter)
        for severity in severities:
            if severity not in SEVERITIES:
                raise PolicyValidationError(
                    f"rule {self.id!r}: unknown severity {severity!r}; "
                    f"expected one of {sorted(SEVERITIES)}"
                )
        object.__setattr__(self, "severity_filter", severities)

        if self.contract_family is not None:
            family = self.contract_family.strip()
            if not family:
                raise PolicyValidationError(
                    f"rule {self.id!r}: 'contract_family' must be non-empty when set"
                )
            object.__setattr__(self, "contract_family", family)

        if self.expires_at is not None:
            object.__setattr__(self, "expires_at", _as_utc(self.expires_at))

        if not self.reason.strip():
            raise PolicyValidationError(f"rule {self.id!r}: 'reason' must be a non-empty string")
        object.__setattr__(self, "reason", self.reason.strip())

    @property
    def scope_kind(self) -> ScopeKind:
        """Classified scope: repo-wide, tenant-wide or a path pattern."""
        if self.scope == SCOPE_REPO:
            return "repo"
        if self.scope == SCOPE_TENANT:
            return "tenant"
        return "path"

    def to_dict(self) -> dict[str, Any]:
        """Canonical serialization (fixed key order) feeding the digest."""
        return {
            "id": self.id,
            "scope": self.scope,
            "action": self.action,
            "severity_filter": list(self.severity_filter),
            "contract_family": self.contract_family,
            "expires_at": _iso_utc(self.expires_at) if self.expires_at is not None else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PolicyDecision:
    """One decision bound to a matched rule, carrying the policy evidence."""

    rule_id: str
    action: str
    reason: str
    scope: str
    scope_kind: ScopeKind
    policy_version: str
    policy_digest: str
    matched_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Fixed key order; suitable for embedding into evidence records."""
        return {
            "rule_id": self.rule_id,
            "action": self.action,
            "reason": self.reason,
            "scope": self.scope,
            "scope_kind": self.scope_kind,
            "matched_path": self.matched_path,
            "policy_version": self.policy_version,
            "policy_digest": self.policy_digest,
        }


@dataclass(frozen=True)
class PolicySet:
    """A loaded, validated policy: version, digest and frozen rules."""

    version: str
    rules: tuple[PolicyRule, ...]
    digest: str

    @classmethod
    def load(cls, path: str | Path) -> PolicySet:
        """Load a policy file (.json/.yaml/.yml) with strict validation."""
        policy_path = Path(path)
        try:
            text = policy_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise PolicyLoadError(f"cannot read policy file {policy_path}: {exc}") from exc
        suffix = policy_path.suffix.lower()
        data: Any
        if suffix == ".json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                raise PolicyLoadError(
                    f"policy file {policy_path} is not valid JSON: {exc}"
                ) from exc
        elif suffix in {".yaml", ".yml"}:
            try:
                data = yaml.safe_load(text)
            except yaml.YAMLError as exc:
                raise PolicyLoadError(
                    f"policy file {policy_path} is not valid YAML: {exc}"
                ) from exc
        else:
            raise PolicyLoadError(
                f"unsupported policy file extension {suffix!r} for {policy_path}; "
                "expected .json, .yaml or .yml"
            )
        return cls.from_dict(data, source=str(policy_path))

    @classmethod
    def from_dict(cls, raw: Any, *, source: str = "<memory>") -> PolicySet:
        """Build a PolicySet from a parsed policy document, failing closed."""
        if not isinstance(raw, dict) or not raw:
            raise PolicyValidationError(f"policy {source}: expected a non-empty object")
        unknown = sorted(set(raw) - _POLICY_FIELDS)
        if unknown:
            raise PolicyValidationError(f"policy {source}: unknown field(s) {unknown}")
        version = raw.get("version")
        if not isinstance(version, str) or not version.strip():
            raise PolicyValidationError(f"policy {source}: 'version' must be a non-empty string")
        rules_raw = raw.get("rules")
        if not isinstance(rules_raw, list) or not rules_raw:
            raise PolicyValidationError(f"policy {source}: 'rules' must be a non-empty list")
        rules: list[PolicyRule] = []
        seen_ids: set[str] = set()
        for index, entry in enumerate(rules_raw):
            rule = cls._parse_rule(entry, source=source, index=index)
            if rule.id in seen_ids:
                raise PolicyValidationError(f"policy {source}: duplicate rule id {rule.id!r}")
            seen_ids.add(rule.id)
            rules.append(rule)
        version_clean = version.strip()
        return cls(
            version=version_clean,
            rules=tuple(rules),
            digest=policy_digest(version_clean, rules),
        )

    @staticmethod
    def _parse_rule(entry: Any, *, source: str, index: int) -> PolicyRule:
        """Parse and construct one rule dict; any mismatch fails closed."""
        where = f"policy {source}: rule[{index}]"
        if not isinstance(entry, dict):
            raise PolicyValidationError(f"{where}: expected an object")
        unknown = sorted(set(entry) - _RULE_FIELDS)
        if unknown:
            raise PolicyValidationError(f"{where}: unknown field(s) {unknown}")
        missing = [field for field in ("id", "scope", "action", "reason") if field not in entry]
        if missing:
            raise PolicyValidationError(f"{where}: missing required field(s) {missing}")
        for field in ("id", "scope", "action", "reason"):
            value = entry[field]
            if not isinstance(value, str) or not value.strip():
                raise PolicyValidationError(f"{where}: '{field}' must be a non-empty string")
        severity_raw = entry.get("severity_filter")
        if severity_raw is not None and (
            not isinstance(severity_raw, list)
            or not all(isinstance(item, str) for item in severity_raw)
        ):
            raise PolicyValidationError(
                f"{where}: 'severity_filter' must be a list of strings"
            )
        family_raw = entry.get("contract_family")
        if family_raw is not None and (not isinstance(family_raw, str) or not family_raw.strip()):
            raise PolicyValidationError(
                f"{where}: 'contract_family' must be a non-empty string when set"
            )
        expires_raw = entry.get("expires_at")
        expires_at: datetime | None = None
        if expires_raw is not None:
            expires_at = _parse_datetime(expires_raw, where=where)
        return PolicyRule(
            id=entry["id"],
            scope=entry["scope"],
            action=entry["action"],
            reason=entry["reason"],
            severity_filter=tuple(severity_raw) if severity_raw is not None else (),
            contract_family=family_raw,
            expires_at=expires_at,
        )


# ── Digest and evaluation ───────────────────────────────────────────────


def policy_digest(version: str, rules: Sequence[PolicyRule]) -> str:
    """SHA-256 over the canonical policy document (stable by construction)."""
    canonical: dict[str, Any] = {
        "schema": DSL_SCHEMA_VERSION,
        "version": version,
        "rules": [rule.to_dict() for rule in sorted(rules, key=lambda rule: rule.id)],
    }
    payload = json.dumps(
        canonical, sort_keys=False, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_paths(raw: Any) -> list[str]:
    """Changed paths in canonical form; non-string entries are dropped."""
    paths: list[str] = []
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if not isinstance(entry, str):
                continue
            normalized = _normalize_path(entry)
            if normalized and normalized != "/":
                paths.append(normalized)
    return paths


def _normalize_severity(raw: Any) -> str | None:
    """Severity uppercased, or None when absent/blank."""
    if isinstance(raw, str):
        normalized = raw.strip().upper()
        if normalized:
            return normalized
    return None


def _normalize_family(raw: Any) -> str | None:
    """Contract family stripped, or None when absent/blank."""
    if isinstance(raw, str):
        normalized = raw.strip()
        if normalized:
            return normalized
    return None


def evaluate_policy(
    policy_set: PolicySet,
    change: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> list[PolicyDecision]:
    """Match a change against every active rule; pure and deterministic.

    ``change`` carries ``paths`` (list of strings),
    ``severity``, ``contract_family`` and ``finding_id`` (the
    id is carried by the caller's evidence, not re-derived here).
    Path-scoped rules match when at least one changed path matches;
    repo/tenant rules match every change. Expired rules are skipped when
    ``now`` is supplied.
    """
    if not isinstance(policy_set, PolicySet):
        raise PolicyEvaluationError("evaluate_policy expects a PolicySet")
    if not isinstance(change, Mapping):
        raise PolicyEvaluationError("evaluate_policy expects a mapping for 'change'")
    if now is not None and not isinstance(now, datetime):
        raise PolicyEvaluationError("'now' must be a datetime or None")
    paths = _normalize_paths(change.get("paths"))
    severity = _normalize_severity(change.get("severity"))
    family = _normalize_family(change.get("contract_family"))
    now_utc = _as_utc(now) if now is not None else None

    matched: list[tuple[tuple[int, str], PolicyRule, str | None]] = []
    for rule in policy_set.rules:
        if (
            rule.expires_at is not None
            and now_utc is not None
            and now_utc >= rule.expires_at
        ):
            continue
        matched_path: str | None = None
        if rule.scope_kind == "path":
            matched_path = next(
                (path for path in paths if _path_matches(path, rule.scope)), None
            )
            if matched_path is None:
                continue
        if rule.severity_filter and (
            severity is None or severity not in rule.severity_filter
        ):
            continue
        if rule.contract_family is not None and family != rule.contract_family:
            continue
        matched.append(((_SCOPE_ORDER[rule.scope_kind], rule.id), rule, matched_path))

    matched.sort(key=lambda item: item[0])
    return [
        PolicyDecision(
            rule_id=rule.id,
            action=rule.action,
            reason=rule.reason,
            scope=rule.scope,
            scope_kind=rule.scope_kind,
            policy_version=policy_set.version,
            policy_digest=policy_set.digest,
            matched_path=matched_path,
        )
        for _, rule, matched_path in matched
    ]
