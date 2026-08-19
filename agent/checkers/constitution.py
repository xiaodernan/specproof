"""Constitution checker (P2-b) — execute "forbidden changes" clauses.

Requirement specs carry explicit FORBIDDEN clauses ("must not remove the
auth guard", "must never publish the event twice"). These are repository
constitution rules: deterministic, diff-checkable, and they must run as
first-class contract checks — not as prose.

Mapping table (clause keyword -> detectable violation):
  annotation removal  -> @PreAuthorize/@Secured/@Transactional/RolesAllowed
                         present in Base, absent in Head on the same method
  duplicate publish   -> convertAndSend( count increased
  unique guard        -> existsByEmail removed
  token invalidation  -> invalidateOldTokens call removed from a method
  schema/field        -> DTO fields removed
"""

from __future__ import annotations

import re
from typing import Any

from agent.checkers.java_source import (
    _FIELD_RE,
    _MUTATING_MAPPINGS,
    _SECURITY_ANNOTATIONS,
    _TOKEN_INVALIDATION_CALLS,
    _split_with_annotations,
)

#: Implementation version of the constitution checker — stamped onto every
#: compiled constitution contract as checker_version (§A task 6).
CHECKER_VERSION = "1.0.0"

_ANNOTATION_RE = re.compile(
    r"@preauthorize|@secured|@transactional|@rolesallowed"
    r"|authenticat|authoriz|permission|\bguard\b|role|transaction",
    re.I,
)
_DUP_PUBLISH_RE = re.compile(r"twice|more than once|duplicate", re.I)
_UNIQUE_RE = re.compile(r"unique|duplicate|already", re.I)
_TOKEN_RE = re.compile(r"token|session|invalidate", re.I)
_SCHEMA_RE = re.compile(r"schema|field|api|compatib", re.I)
_REMOVE_RE = re.compile(r"remove|delete|drop|without|no longer", re.I)


def _per_method_pairs(
    base_files: dict[str, str], head_files: dict[str, str],
) -> list[tuple[str, str, str, str]]:
    """[(file, method_name, base_block, head_block)] for shared methods."""
    out: list[tuple[str, str, str, str]] = []
    for rel, base in base_files.items():
        head = head_files.get(rel)
        if head is None:
            continue
        base_methods = {
            name: block for block, name in _split_with_annotations(base)
        }
        head_methods = {
            name: block for block, name in _split_with_annotations(head)
        }
        for name, block in base_methods.items():
            if name in head_methods:
                out.append((rel, name, block, head_methods[name]))
    return out


def check_forbidden_changes(
    base_files: dict[str, str],
    head_files: dict[str, str],
    forbidden_clauses: list[str],
    contract_id: str,
) -> list[dict[str, Any]]:
    """Run the constitution rules. Findings carry the CONTRACT's id."""
    findings: list[dict[str, Any]] = []

    for clause in forbidden_clauses:
        lowered = clause.lower()
        is_remove = bool(_REMOVE_RE.search(lowered))

        if _ANNOTATION_RE.search(lowered):
            for rel, name, base_block, head_block in _per_method_pairs(base_files, head_files):
                base_ann = (
                    any(a in base_block for a in _SECURITY_ANNOTATIONS)
                    or "@Transactional" in base_block
                )
                head_ann = (
                    any(a in head_block for a in _SECURITY_ANNOTATIONS)
                    or "@Transactional" in head_block
                )
                mutating = (
                    any(m in base_block for m in _MUTATING_MAPPINGS)
                    or any(m in head_block for m in _MUTATING_MAPPINGS)
                )
                if is_remove and base_ann and not head_ann and mutating:
                    findings.append({
                        "id": "CONST-" + contract_id,
                        "contract_id": contract_id,
                        "severity": "MAJOR",
                        "type": "forbidden_annotation_removal",
                        "description": (
                            "Forbidden change detected: " + clause
                            + " — method " + name + "() in " + rel
                        ),
                        "evidence_type": "constitution_check",
                        "confidence": 0.85,
                        "location": rel,
                        "source": "constitution_checker",
                    })

        if _DUP_PUBLISH_RE.search(lowered):
            for rel, base in base_files.items():
                head = head_files.get(rel)
                if head is None:
                    continue
                if head.count("convertAndSend(") > base.count("convertAndSend("):
                    findings.append({
                        "id": "CONST-" + contract_id,
                        "contract_id": contract_id,
                        "severity": "MAJOR",
                        "type": "forbidden_duplicate_publish",
                        "description": (
                            "Forbidden change detected: " + clause
                            + " — publish count increased in " + rel
                        ),
                        "evidence_type": "constitution_check",
                        "confidence": 0.85,
                        "location": rel,
                        "source": "constitution_checker",
                    })

        if _UNIQUE_RE.search(lowered) and is_remove:
            for rel, base in base_files.items():
                head = head_files.get(rel)
                if head is None or "existsByEmail" not in base:
                    continue
                if "existsByEmail" not in head:
                    findings.append({
                        "id": "CONST-" + contract_id,
                        "contract_id": contract_id,
                        "severity": "MAJOR",
                        "type": "forbidden_guard_removal",
                        "description": (
                            "Forbidden change detected: " + clause
                            + " — uniqueness guard removed in " + rel
                        ),
                        "evidence_type": "constitution_check",
                        "confidence": 0.85,
                        "location": rel,
                        "source": "constitution_checker",
                    })

        if _TOKEN_RE.search(lowered) and is_remove:
            for rel, name, base_block, head_block in _per_method_pairs(base_files, head_files):
                base_call = any(c in base_block for c in _TOKEN_INVALIDATION_CALLS)
                head_call = any(c in head_block for c in _TOKEN_INVALIDATION_CALLS)
                if base_call and not head_call:
                    findings.append({
                        "id": "CONST-" + contract_id,
                        "contract_id": contract_id,
                        "severity": "MAJOR",
                        "type": "forbidden_token_guard_removal",
                        "description": (
                            "Forbidden change detected: " + clause
                            + " — token invalidation removed from "
                            + name + "() in " + rel
                        ),
                        "evidence_type": "constitution_check",
                        "confidence": 0.85,
                        "location": rel,
                        "source": "constitution_checker",
                    })

        if _SCHEMA_RE.search(lowered) and is_remove:
            for rel, base in base_files.items():
                head = head_files.get(rel)
                if head is None:
                    continue
                is_dto = (
                    ("/dto/" in rel)
                    or rel.endswith("Request.java")
                    or rel.endswith("Response.java")
                )
                if not is_dto:
                    continue
                removed = set(_FIELD_RE.findall(base)) - set(_FIELD_RE.findall(head))
                if removed:
                    findings.append({
                        "id": "CONST-" + contract_id,
                        "contract_id": contract_id,
                        "severity": "MAJOR",
                        "type": "forbidden_schema_break",
                        "description": (
                            "Forbidden change detected: " + clause
                            + " — fields removed in " + rel + ": "
                            + str(sorted(removed))
                        ),
                        "evidence_type": "constitution_check",
                        "confidence": 0.85,
                        "location": rel,
                        "source": "constitution_checker",
                    })

    return findings
