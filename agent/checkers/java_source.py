"""Deterministic Java source-diff checkers for SpecProof contracts.

Input: base_files / head_files — dicts mapping relative paths (posix)
of src/main Java files to their content.

Each checker emits findings with:
  id, contract_id, severity (<= MAJOR), type, description,
  evidence_type="java_source_diff", confidence (<= 0.85), location, source.

contract_results_for converts findings + base observation into per-contract
results: FAIL when a violation is found, PASS when the checker ran and found
the guarded construct intact, UNVERIFIED when the construct was absent in
both versions (nothing to check).
"""
from __future__ import annotations

import re
from typing import Any

#: Implementation version of this checker module — stamped onto every
#: compiled contract as checker_version (industrialization §A task 6).
#: Bump whenever checker rules change; stored contracts keep the version
#: they were compiled with (version semantics are immutable/append-only).
CHECKER_VERSION = "2.0.0"

_MUTATING_MAPPINGS = ("@PutMapping", "@PostMapping", "@DeleteMapping", "@PatchMapping")

# Method-security annotations. Beyond the Spring built-ins, this set covers
# COMPOSED custom annotations in common enterprise use (@RequireAuth etc.):
# the checker reads source text heuristically and cannot resolve
# meta-annotations, so the equivalence set is the documented approximation
# for the Spring-specialized product scope (PRODUCTION_SPEC 第 2 节).
_SECURITY_ANNOTATIONS = (
    "@PreAuthorize", "@Secured", "@RolesAllowed", "@RequireAuth",
    "@Authenticated",
)
_WRITE_OPS = (".save(", ".saveAndFlush(", ".delete(", ".deleteAll(", ".update(")

# Annotation group: @Name, optionally with one level of nested parens,
# e.g. @PreAuthorize("isAuthenticated()"). The old form ([^)]*) silently
# dropped such annotations from the method block, which made the AUTH-01
# checker blind to the flagship regression.
#
# All quantifiers are POSSESSIVE (*+, ++, ?+): the original backtrackable
# form degenerated into exponential backtracking on entity files full of
# @Column annotations (minutes per file → the splitter appeared to hang).
_SPLIT_RE = re.compile(
    # Outer annotation repetition is possessive (prevents exponential
    # partitioning on entity files), the paren content stays backtrackable
    # (nested parens like @PreAuthorize("isAuthenticated()") need it).
    r"((?:(?:@\w++(?:\((?:[^()]*|\([^()]*\))*\))?\s*+)*+))"
    r"(?:public|private|protected|static|final|default|\s)+"
    r"[\w<>,\[\]\s]+\s+(\w+)\s*\([^)]*\)\s*(?:throws[^{]+)?\{"
)

_FIELD_RE = re.compile(r"private\s+[\w<>,.\[\] ]+\s+(\w+)\s*;")


def _split_with_annotations(content: str) -> list[tuple[str, str]]:
    """Return [(annotations+method_block, method_name)] with annotations included."""
    out: list[tuple[str, str]] = []
    for m in _SPLIT_RE.finditer(content):
        ann = m.group(1) or ""
        start = m.end() - 1
        depth = 0
        i = start
        while i < len(content):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out.append((ann + content[m.end() - 1:i + 1], m.group(2)))
    return out


def _has_security_annotation(method_block: str) -> bool:
    return any(ann in method_block for ann in _SECURITY_ANNOTATIONS)


def _finding(
    contract_id: str,
    ftype: str,
    description: str,
    location: str,
    severity: str = "MAJOR",
    confidence: float = 0.85,
) -> dict[str, Any]:
    from agent.checkers.registry import normalize_location

    return {
        "id": "SRC-" + contract_id.split("-")[0] + "-" + ftype[:4].upper(),
        "contract_id": contract_id,
        "severity": severity,
        "type": ftype,
        "description": description,
        "evidence_type": "java_source_diff",
        "confidence": confidence,
        "location": str(normalize_location(location)["path"]),
        "source": "contract_checker",
    }


def _implemented_interface_names(class_text: str) -> list[str]:
    """Parse the implements clause of a controller class declaration."""
    match = re.search(
        r"class\s+\w+\s+implements\s+([\w.,\s]+?)\s*\{", class_text
    )
    if not match:
        return []
    return [
        part.strip()
        for part in match.group(1).split(",")
        if part.strip()
    ]


def _interface_protects_method(
    name: str, interface_names: list[str], head_files: dict[str, str],
) -> bool:
    """True when an implemented interface method carries a security
    annotation (Spring resolves interface-level method security through
    JDK dynamic proxies). Interface methods may be abstract (no body), so
    this scans for an annotation shortly before the method declaration
    instead of reusing the body-based splitter."""
    annotations = "|".join(re.escape(a) for a in _SECURITY_ANNOTATIONS)
    for interface_name in interface_names:
        for rel, content in head_files.items():
            if not rel.endswith(interface_name + ".java"):
                continue
            pattern = re.compile(
                r"(?:"
                + annotations
                + r")[\s\S]{0,400}?\b"
                + re.escape(name)
                + r"\s*\("
            )
            if pattern.search(content):
                return True
    return False


def check_auth_annotations(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict[str, Any]]:
    """AUTH-01: security annotations must not be removed from mutating endpoints.

    Protection is considered intact when the head method block carries a
    security annotation (built-in or composed custom), OR when an
    implemented interface's default method carries one — both are real
    Spring method-security resolution paths.
    """
    findings: list[dict[str, Any]] = []
    for rel in sorted(base_files):
        if not rel.endswith("Controller.java"):
            continue
        head = head_files.get(rel)
        if head is None:
            continue
        base_methods = _split_with_annotations(base_files[rel])
        head_methods = {
            name: block for block, name in _split_with_annotations(head)
        }
        interface_names = _implemented_interface_names(head)

        for block, name in base_methods:
            mutating = any(m in block for m in _MUTATING_MAPPINGS)
            if not mutating or not _has_security_annotation(block):
                continue
            head_block = head_methods.get(name)
            if head_block is not None and not _has_security_annotation(head_block):
                if _interface_protects_method(name, interface_names, head_files):
                    continue
                findings.append(_finding(
                    "AUTH-01",
                    "annotation_removed",
                    "Security annotation removed from mutating endpoint method "
                    + name + "() in " + rel,
                    rel,
                ))
    return findings


def check_transactional(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict[str, Any]]:
    """TRANSACTION-01: write methods must not lose @Transactional, and write
    operations must not move outside a transaction boundary."""
    findings: list[dict[str, Any]] = []
    for rel in sorted(base_files):
        if not rel.endswith("Service.java"):
            continue
        head = head_files.get(rel)
        if head is None:
            continue
        base_methods = _split_with_annotations(base_files[rel])
        head_methods = {
            name: block for block, name in _split_with_annotations(head)
        }

        for block, name in base_methods:
            writes = any(op in block for op in _WRITE_OPS)
            if not writes:
                continue
            base_tx = "@Transactional" in block
            head_block = head_methods.get(name)
            if head_block is None:
                continue
            head_tx = "@Transactional" in head_block
            if base_tx and not head_tx:
                findings.append(_finding(
                    "TRANSACTION-01",
                    "annotation_removed",
                    "@Transactional removed from write method " + name + "() in "
                    + rel + " — data operations may no longer be atomic",
                    rel,
                ))
            elif not head_tx:
                write_count = sum(head_block.count(op) for op in _WRITE_OPS)
                if write_count >= 2:
                    findings.append(_finding(
                        "TRANSACTION-01",
                        "transaction_split",
                        "Method " + name + "() in " + rel + " performs "
                        + str(write_count) + " write operations without @Transactional",
                        rel,
                    ))
    return findings


def check_unique_email(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict[str, Any]]:
    """UNIQUE-01: the duplicate-email guard must not be removed."""
    findings: list[dict[str, Any]] = []
    for rel in sorted(base_files):
        base = base_files[rel]
        head = head_files.get(rel)
        if head is None or "existsByEmail" not in base:
            continue
        if "existsByEmail" not in head:
            findings.append(_finding(
                "UNIQUE-01",
                "guard_removed",
                "Duplicate-email guard (existsByEmail) removed in " + rel,
                rel,
            ))
    return findings


_TOKEN_INVALIDATION_CALLS = (
    "invalidateOldTokens(",
    "redisTemplate.delete(",
    "invalidateTokens(",
)


def check_token_invalidation(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict[str, Any]]:
    """TOKEN_INVALIDATION-01: old token invalidation must not be removed.

    Compares token-invalidation CALL SITES per method, not whole-file string
    presence. Removing the call while keeping the (now dead) private method —
    the case-05 golden regression — is still detected.
    """
    findings: list[dict[str, Any]] = []
    for rel in sorted(base_files):
        base = base_files[rel]
        head = head_files.get(rel)
        if head is None:
            continue

        base_has_call = any(c in base for c in _TOKEN_INVALIDATION_CALLS)
        if not base_has_call:
            continue
        head_has_call = any(c in head for c in _TOKEN_INVALIDATION_CALLS)

        if not head_has_call:
            findings.append(_finding(
                "TOKEN_INVALIDATION-01",
                "guard_removed",
                "Token invalidation logic removed from " + rel
                + " — old tokens stay valid after email change",
                rel,
            ))
            continue

        # Call still exists somewhere: check per-method removal.
        base_methods = {
            name: block for block, name in _split_with_annotations(base)
        }
        head_methods = {
            name: block for block, name in _split_with_annotations(head)
        }
        for name, block in base_methods.items():
            if not any(c in block for c in _TOKEN_INVALIDATION_CALLS):
                continue
            head_block = head_methods.get(name)
            if head_block is not None and not any(
                c in head_block for c in _TOKEN_INVALIDATION_CALLS
            ):
                findings.append(_finding(
                    "TOKEN_INVALIDATION-01",
                    "guard_removed",
                    "Token invalidation call removed from method "
                    + name + "() in " + rel
                    + " — old tokens stay valid after email change",
                    rel,
                ))
    return findings


def check_event_once(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict[str, Any]]:
    """EVENT_ONCE-01: an event must not be published more often than in Base."""
    findings: list[dict[str, Any]] = []
    for rel in sorted(base_files):
        base = base_files[rel]
        head = head_files.get(rel)
        if head is None:
            continue
        base_count = base.count("convertAndSend(")
        head_count = head.count("convertAndSend(")
        if base_count >= 1 and head_count > base_count:
            findings.append(_finding(
                "EVENT_ONCE-01",
                "duplicate_publish",
                "Event publish count increased in " + rel + ": "
                + str(base_count) + " -> " + str(head_count),
                rel,
            ))
    return findings


def check_endpoint_changes(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict[str, Any]]:
    """OPENAPI-01: the public endpoint surface must not shrink or change.

    Compares (HTTP verb, path) pairs per controller between Base and Head.
    Removing or renaming an endpoint, or changing its verb, is a backward
    compatibility break for API consumers.
    """
    findings: list[dict[str, Any]] = []
    mapping_re = re.compile(r'@\w*Mapping\("([^"]+)"\)')

    def _surface(source: str) -> set[tuple[str, str]]:
        # The PUBLIC surface is (verb, path) ONLY. The Java method name is
        # an internal detail: renaming getUser() to fetchUser() must not
        # be flagged as an endpoint removal (refactor precision).
        out: set[tuple[str, str]] = set()
        for block, _name in _split_with_annotations(source):
            m = mapping_re.search(block)
            if not m:
                continue
            path = m.group(1)
            if "GetMapping" in block:
                verb = "GET"
            else:
                verb = next(
                    (
                        vm[1:].replace("Mapping", "").upper()
                        for vm in _MUTATING_MAPPINGS if vm in block
                    ),
                    "UNKNOWN",
                )
            out.add((verb, path))
        return out

    for rel in sorted(base_files):
        if not rel.endswith("Controller.java"):
            continue
        head = head_files.get(rel)
        if head is None:
            continue
        removed = _surface(base_files[rel]) - _surface(head)
        for verb, path in sorted(removed):
            findings.append(_finding(
                "OPENAPI-01",
                "endpoint_removed",
                "Endpoint " + verb + " " + path + " "
                "present in Base but missing or changed in Head "
                "— API surface break",
                rel,
            ))
    return findings


def check_schema_compat(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict[str, Any]]:
    """BACKWARD_COMPATIBLE-01: API DTO fields must not be removed or renamed."""
    findings: list[dict[str, Any]] = []
    for rel in sorted(base_files):
        base = base_files[rel]
        head = head_files.get(rel)
        if head is None:
            continue
        is_dto = ("/dto/" in rel) or rel.endswith("Request.java") or rel.endswith("Response.java")
        if not is_dto:
            continue
        base_fields = set(_FIELD_RE.findall(base))
        head_fields = set(_FIELD_RE.findall(head))
        removed = base_fields - head_fields
        if removed:
            findings.append(_finding(
                "BACKWARD_COMPATIBLE-01",
                "schema_break",
                "API schema fields removed or renamed in " + rel + ": "
                + str(sorted(removed)),
                rel,
            ))
    return findings


_ALL_CHECKERS = [
    check_auth_annotations,
    check_transactional,
    check_unique_email,
    check_token_invalidation,
    check_event_once,
    check_schema_compat,
    check_endpoint_changes,
]


def run_contract_checks(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict[str, Any]]:
    """Run the registered checkers (§14.1 registry) and return deduplicated
    findings. A crashing checker becomes CHECKER_FAILED evidence — never an
    empty result that reads as "no problems found"."""
    from agent.checkers.registry import run_registered_checks

    findings, failures, note = run_registered_checks(base_files, head_files)
    if note is not None:
        # Unsupported target: fail closed with an explicit explanation
        # instead of pretending the sources are clean.
        return [{
            "id": "CHECKER-MATRIX-NOT_IMPLEMENTED",
            "contract_id": "CHECKER_FAILED",
            "severity": "NONE",
            "type": "checker_failed",
            "description": note,
            "evidence_type": "checker_failed",
            "confidence": 1.0,
            "location": "agent/checkers/registry.py",
            "source": "checker_registry",
        }]
    findings.extend(failures)

    failed: list[dict[str, Any]] = [
        f for f in findings if f.get("type") == "checker_failed"
    ]
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for f in findings:
        if f.get("type") == "checker_failed":
            continue  # failures are evidence; never deduped away
        key = (f["contract_id"], f["type"])
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = f
        else:
            if f["confidence"] > existing["confidence"]:
                deduped[key] = f
            if f["description"] not in existing["description"]:
                existing["description"] = (
                    existing["description"] + " | " + f["description"]
                )
    return list(deduped.values()) + failed


def contract_results_for(
    contracts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    base_files: dict[str, str],
    base_schema_present: bool = False,
    base_test_present: bool = False,
) -> list[dict[str, Any]]:
    """Map checker findings onto per-contract results.

    FAIL       a checker found a violation of this contract
    PASS       a checker ran against a guarded construct and found it intact
    UNVERIFIED no checker could observe this contract's construct at all

    P6: MIGRATION-01 / TEST_STRENGTH-01 observability comes from schema.sql
    and the test sources, passed in by run_static_checks.
    """
    findings_by_contract: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        findings_by_contract.setdefault(f["contract_id"], []).append(f)

    base_observed: dict[str, bool] = {
        "AUTH-01": any(
            _has_security_annotation(b) and any(m in b for m in _MUTATING_MAPPINGS)
            for rel, c in base_files.items() if rel.endswith("Controller.java")
            for b, _n in _split_with_annotations(c)
        ),
        "TRANSACTION-01": any(
            "@Transactional" in c
            for rel, c in base_files.items() if rel.endswith("Service.java")
        ),
        "UNIQUE-01": any("existsByEmail" in c for c in base_files.values()),
        "TOKEN_INVALIDATION-01": any(
            "invalidateOldTokens" in c or "redisTemplate.delete" in c
            for c in base_files.values()
        ),
        "EVENT_ONCE-01": any("convertAndSend(" in c for c in base_files.values()),
        "BACKWARD_COMPATIBLE-01": any(
            ("/dto/" in rel) or rel.endswith("Request.java") or rel.endswith("Response.java")
            for rel in base_files
        ),
        "OPENAPI-01": any(
            any(m in c for m in _MUTATING_MAPPINGS) or "GetMapping" in c
            for rel, c in base_files.items() if rel.endswith("Controller.java")
        ),
        "MIGRATION-01": base_schema_present,
        "TEST_STRENGTH-01": base_test_present,
    }

    # A crashing checker must never let its contract family PASS by silence:
    # contracts whose family checker failed stay UNVERIFIED with the reason.
    failed_families: set[str] = {
        family
        for f in findings
        if f.get("type") == "checker_failed"
        for family in f.get("families", [])
    }

    results: list[dict[str, Any]] = []
    for contract in contracts:
        cid = contract.get("id", "")
        hits = findings_by_contract.get(cid, [])
        if hits:
            results.append({
                "contract_id": cid,
                "result": "FAIL",
                "experiment": "java_source_diff",
                "evidence_ref": hits[0]["id"],
                "details": "; ".join(h["description"] for h in hits),
            })
        elif cid in failed_families:
            results.append({
                "contract_id": cid,
                "result": "UNVERIFIED",
                "experiment": "java_source_diff",
                "evidence_ref": "CHECKER_FAILED",
                "details": (
                    "checker for this contract family crashed — "
                    "never PASS by silence"
                ),
            })
        elif base_observed.get(cid):
            results.append({
                "contract_id": cid,
                "result": "PASS",
                "experiment": "java_source_diff",
                "evidence_ref": "no violation found in source diff",
                "details": "Checker ran; guarded construct intact in Head",
            })
        else:
            results.append({
                "contract_id": cid,
                "result": "UNVERIFIED",
                "experiment": "java_source_diff",
                "evidence_ref": None,
                "details": "No observable construct for this contract in Base",
            })
    return results
