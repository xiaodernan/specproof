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

_MUTATING_MAPPINGS = ("@PutMapping", "@PostMapping", "@DeleteMapping", "@PatchMapping")
_SECURITY_ANNOTATIONS = ("@PreAuthorize", "@Secured", "@RolesAllowed")
_WRITE_OPS = (".save(", ".saveAndFlush(", ".delete(", ".deleteAll(", ".update(")

_SPLIT_RE = re.compile(
    r"((?:@\w+(?:\([^)]*\))?\s*)*)"
    r"(?:public|private|protected|static|final|\s)+"
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
) -> dict:
    return {
        "id": "SRC-" + contract_id.split("-")[0] + "-" + ftype[:4].upper(),
        "contract_id": contract_id,
        "severity": severity,
        "type": ftype,
        "description": description,
        "evidence_type": "java_source_diff",
        "confidence": confidence,
        "location": location,
        "source": "contract_checker",
    }


def check_auth_annotations(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict]:
    """AUTH-01: security annotations must not be removed from mutating endpoints."""
    findings: list[dict] = []
    for rel in sorted(base_files):
        if not rel.endswith("Controller.java"):
            continue
        head = head_files.get(rel)
        if head is None:
            continue
        base_methods = _split_with_annotations(base_files[rel])
        head_methods = dict(
            (name, block) for block, name in _split_with_annotations(head)
        )

        for block, name in base_methods:
            mutating = any(m in block for m in _MUTATING_MAPPINGS)
            if not mutating or not _has_security_annotation(block):
                continue
            head_block = head_methods.get(name)
            if head_block is not None and not _has_security_annotation(head_block):
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
) -> list[dict]:
    """TRANSACTION-01: write methods must not lose @Transactional, and write
    operations must not move outside a transaction boundary."""
    findings: list[dict] = []
    for rel in sorted(base_files):
        if not rel.endswith("Service.java"):
            continue
        head = head_files.get(rel)
        if head is None:
            continue
        base_methods = _split_with_annotations(base_files[rel])
        head_methods = dict(
            (name, block) for block, name in _split_with_annotations(head)
        )

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
) -> list[dict]:
    """UNIQUE-01: the duplicate-email guard must not be removed."""
    findings: list[dict] = []
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


def check_token_invalidation(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict]:
    """TOKEN_INVALIDATION-01: old token invalidation must not be removed."""
    findings: list[dict] = []
    for rel in sorted(base_files):
        base = base_files[rel]
        head = head_files.get(rel)
        if head is None:
            continue
        if "invalidateOldTokens" not in base and "redisTemplate.delete" not in base:
            continue
        if "invalidateOldTokens" not in head and "redisTemplate.delete" not in head:
            findings.append(_finding(
                "TOKEN_INVALIDATION-01",
                "guard_removed",
                "Token invalidation logic removed in " + rel
                + " — old tokens stay valid after email change",
                rel,
            ))
    return findings


def check_event_once(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict]:
    """EVENT_ONCE-01: an event must not be published more often than in Base."""
    findings: list[dict] = []
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


def check_schema_compat(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict]:
    """BACKWARD_COMPATIBLE-01: API DTO fields must not be removed or renamed."""
    findings: list[dict] = []
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
]


def run_contract_checks(
    base_files: dict[str, str], head_files: dict[str, str]
) -> list[dict]:
    """Run all checkers and return deduplicated findings."""
    findings: list[dict] = []
    for checker in _ALL_CHECKERS:
        findings.extend(checker(base_files, head_files))

    deduped: dict[tuple[str, str], dict] = {}
    for f in findings:
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
    return list(deduped.values())


def contract_results_for(
    contracts: list[dict],
    findings: list[dict],
    base_files: dict[str, str],
) -> list[dict]:
    """Map checker findings onto per-contract results.

    FAIL       a checker found a violation of this contract
    PASS       a checker ran against a guarded construct and found it intact
    UNVERIFIED no checker could observe this contract's construct at all
    """
    findings_by_contract: dict[str, list[dict]] = {}
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
    }

    results: list[dict] = []
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

