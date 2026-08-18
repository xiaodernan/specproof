"""Deterministic, evidence-driven fix proposals (P5 fix approval flow).

Spec 6.2 PR commands: /specproof fix proposes fixes for confirmed findings;
/specproof approve FIX_ID applies + verifies the approved fix.

A proposal is ONLY created when the fix is a mechanical restoration of Base
behavior that the diff actually shows:

- annotation_removed (AUTH-01 / TRANSACTION-01): re-insert the annotation
  line(s) the Head file lost, in front of the same method signature;
- guard_removed (TOKEN_INVALIDATION-01): re-insert the token-invalidation
  call inside the same method body;
- duplicate_publish (EVENT_ONCE-01): remove the extra publish call, or
  restore the Base publish line when the call itself changed (wrong routing
  key);
- validation_removed (UNIQUE-01): re-insert the removed @NotBlank/@NotNull
  annotation in front of the same DTO field.

Anything else — or any case where the anchor cannot be matched exactly — is
skipped with a reason. SpecProof never fabricates a patch: an applied fix
must be verifiable, and an unverifiable anchor is reported, not guessed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_ANNOTATION_CONTRACTS = {"AUTH-01", "TRANSACTION-01", "OPENAPI-01"}
_TOKEN_CONTRACTS = {"TOKEN_INVALIDATION-01"}
_EVENT_CONTRACTS = {"EVENT_ONCE-01", "EVENT-01"}
_VALIDATION_CONTRACTS = {"UNIQUE-01"}

_ANNOTATION_RE = re.compile(r"^\s*@\w+")
_TOKEN_CALL_RE = re.compile(
    r"(invalidateOldTokens|redisTemplate\.delete)\s*\("
)
_PUBLISH_RE = re.compile(r"convertAndSend\s*\(")
_VALIDATION_RE = re.compile(r"^\s*@(NotBlank|NotNull|Size|Email|Valid)\b")
_FIELD_RE = re.compile(
    r"^\s*(?:private|public|protected)\s+[\w<>,\[\] ]+\s+(\w+)\s*[;=]"
)
_METHOD_NAME_FROM_DESC = re.compile(r"method\s+(\w+)\s*\(")


@dataclass(frozen=True)
class FixProposal:
    """One deterministic fix candidate, anchored to an exact Head line."""

    fix_id: str
    finding_id: str
    contract_id: str
    path: str
    action: str  # insert_lines | replace_lines | remove_lines
    anchor_line: int  # 1-based line in the Head file
    head_context: str  # exact line content expected at anchor (drift guard)
    base_lines: list[str]
    head_lines: list[str]
    rationale: str
    patch: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _java_files(root: Path) -> dict[str, Path]:
    """Relative path -> absolute path for every .java file (no target/)."""
    out: dict[str, Path] = {}
    if not root.is_dir():
        return out
    for path in root.rglob("*.java"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("target/"):
            continue
        out[rel] = path
    return out


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _method_bounds(lines: list[str], name: str) -> tuple[int, int] | None:
    """(signature_line, close_brace_line), 0-based, for method name."""
    for i, line in enumerate(lines):
        if re.search(rf"\b{re.escape(name)}\s*\(", line):
            depth = 0
            opened = False
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if lines[j].count("{") > 0:
                    opened = True
                if opened and depth <= 0:
                    return i, j
            return None
    return None


def _name_from_signature(lines: list[str], annotation_index: int) -> str | None:
    for j in range(annotation_index + 1, min(len(lines), annotation_index + 6)):
        match = re.search(r"\b(\w+)\s*\([^;]*\)\s*(\{{|throws)", lines[j])
        if match:
            return match.group(1)
    return None


def _annotation_lines_above(
    lines: list[str], signature_line: int
) -> list[int]:
    """Indices of contiguous annotation lines directly above a signature."""
    indices: list[int] = []
    i = signature_line - 1
    while i >= 0 and _ANNOTATION_RE.match(lines[i]):
        indices.append(i)
        i -= 1
    return list(reversed(indices))


def _method_name_from(finding: dict[str, Any]) -> str | None:
    description = finding.get("description") or ""
    match = _METHOD_NAME_FROM_DESC.search(description)
    if match:
        return match.group(1)
    return None


def _field_name_from_declaration(line: str) -> str | None:
    match = _FIELD_RE.match(line)
    return match.group(1) if match else None


def _unified_patch(
    path: str, head_lines: list[str], new_lines: list[str]
) -> str:
    diff = difflib.unified_diff(
        head_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(diff)


def _restore_annotation(
    finding: dict[str, Any], base_lines: list[str], head_lines: list[str]
) -> FixProposal | None:
    method_name = _method_name_from(finding)
    base_bounds: tuple[int, int] | None = None
    head_bounds: tuple[int, int] | None = None
    if method_name:
        base_bounds = _method_bounds(base_lines, method_name)
        head_bounds = _method_bounds(head_lines, method_name)
    if base_bounds is None and method_name is None:
        # Fallback: exactly one Base method carries annotations that the
        # Head version of the same method lost.
        candidates: list[tuple[int, int]] = []
        for i, line in enumerate(base_lines):
            if not _ANNOTATION_RE.match(line):
                continue
            name = _name_from_signature(base_lines, i)
            if not name:
                continue
            bounds = _method_bounds(base_lines, name)
            if bounds and _annotation_lines_above(base_lines, bounds[0]):
                candidates.append(bounds)
        if len(candidates) == 1:
            base_bounds = candidates[0]
            method_name = _name_from_signature(
                base_lines, base_bounds[0]
            )
    if base_bounds is None or method_name is None:
        return None
    head_bounds = _method_bounds(head_lines, method_name)
    if head_bounds is None:
        return None
    base_signature = base_bounds[0]
    base_annos = [
        base_lines[i]
        for i in _annotation_lines_above(base_lines, base_signature)
    ]
    if not base_annos:
        return None
    head_signature = head_bounds[0]
    head_annos = {
        head_lines[j]
        for j in _annotation_lines_above(head_lines, head_signature)
    }
    removed = [line for line in base_annos if line not in head_annos]
    if not removed:
        return None  # Head kept every Base annotation — nothing to restore.
    head_context = head_lines[head_signature]
    patch = _unified_patch(
        str(finding["location"]),
        head_lines,
        head_lines[:head_signature] + removed + head_lines[head_signature:],
    )
    return FixProposal(
        fix_id="",
        finding_id=str(finding.get("id", "")),
        contract_id=str(finding.get("contract_id", "")),
        path=str(finding["location"]),
        action="insert_lines",
        anchor_line=head_signature + 1,
        head_context=head_context,
        base_lines=removed,
        head_lines=[],
        rationale="Restore the annotation(s) Head removed from "
        f"method {method_name}()",
        patch=patch,
    )


def _restore_token_call(
    finding: dict[str, Any], base_lines: list[str], head_lines: list[str]
) -> FixProposal | None:
    method_name = _method_name_from(finding)
    if not method_name:
        return None
    base_bounds = _method_bounds(base_lines, method_name)
    if base_bounds is None:
        return None
    base_start, base_end = base_bounds
    removed_calls = [
        line
        for line in base_lines[base_start:base_end + 1]
        if _TOKEN_CALL_RE.search(line)
    ]
    if not removed_calls:
        return None
    head_bounds = _method_bounds(head_lines, method_name)
    if head_bounds is None:
        return None
    head_start, head_end = head_bounds
    if any(
        _TOKEN_CALL_RE.search(line)
        for line in head_lines[head_start:head_end + 1]
    ):
        return None  # Head still has the call — nothing to restore.
    anchor = head_end  # insert before the method's closing brace
    head_context = head_lines[anchor]
    patch = _unified_patch(
        str(finding["location"]),
        head_lines,
        head_lines[:anchor] + removed_calls + head_lines[anchor:],
    )
    return FixProposal(
        fix_id="",
        finding_id=str(finding.get("id", "")),
        contract_id=str(finding.get("contract_id", "")),
        path=str(finding["location"]),
        action="insert_lines",
        anchor_line=anchor + 1,
        head_context=head_context,
        base_lines=removed_calls,
        head_lines=[],
        rationale="Restore the token-invalidation call Head removed from "
        f"method {method_name}()",
        patch=patch,
    )


def _restore_event(
    finding: dict[str, Any], base_lines: list[str], head_lines: list[str]
) -> FixProposal | None:
    base_publish = [
        (i, line)
        for i, line in enumerate(base_lines)
        if _PUBLISH_RE.search(line)
    ]
    head_publish = [
        (i, line)
        for i, line in enumerate(head_lines)
        if _PUBLISH_RE.search(line)
    ]
    if not base_publish:
        return None
    if len(head_publish) > len(base_publish):
        # Duplicate publish: remove exactly one extra Head line when the
        # Base line is still present (the case-07 pattern: Base 1 -> Head 2).
        if len(base_publish) != 1 or len(head_publish) != 2:
            return None
        base_text = base_publish[0][1].strip()
        extras = [p for p in head_publish if p[1].strip() != base_text]
        if extras:
            if len(extras) != 1:
                return None
            index, line = extras[0]
        else:
            # Both Head lines are verbatim copies of the Base line — the
            # duplicate is the second occurrence.
            index, line = head_publish[1]
        patch = _unified_patch(
            str(finding["location"]),
            head_lines,
            head_lines[:index] + head_lines[index + 1:],
        )
        return FixProposal(
            fix_id="",
            finding_id=str(finding.get("id", "")),
            contract_id=str(finding.get("contract_id", "")),
            path=str(finding["location"]),
            action="remove_lines",
            anchor_line=index + 1,
            head_context=line,
            base_lines=[],
            head_lines=[line],
            rationale="Remove the duplicate event publish Head added",
            patch=patch,
        )
    if len(head_publish) == len(base_publish) == 1:
        base_index, base_line = base_publish[0]
        head_index, head_line = head_publish[0]
        if base_line.strip() == head_line.strip():
            return None  # identical — nothing to restore.
        patch = _unified_patch(
            str(finding["location"]),
            head_lines,
            head_lines[:head_index] + [base_line] + head_lines[head_index + 1:],
        )
        return FixProposal(
            fix_id="",
            finding_id=str(finding.get("id", "")),
            contract_id=str(finding.get("contract_id", "")),
            path=str(finding["location"]),
            action="replace_lines",
            anchor_line=head_index + 1,
            head_context=head_line,
            base_lines=[base_line],
            head_lines=[head_line],
            rationale="Restore the Base publish call (exchange/routing key)",
            patch=patch,
        )
    return None


def _restore_validation(
    finding: dict[str, Any], base_lines: list[str], head_lines: list[str]
) -> FixProposal | None:
    removed: list[str] = []
    field_name: str | None = None
    for i, line in enumerate(base_lines):
        if not _VALIDATION_RE.match(line):
            continue
        for j in range(i + 1, min(len(base_lines), i + 4)):
            if _VALIDATION_RE.match(base_lines[j]):
                continue
            candidate = _field_name_from_declaration(base_lines[j])
            if candidate:
                removed.append(line)
                field_name = candidate
                break
    if len(removed) != 1 or field_name is None:
        return None  # ambiguous or nothing removed — skip honestly.
    head_index: int | None = None
    for i, line in enumerate(head_lines):
        if _field_name_from_declaration(line) == field_name:
            if any(
                _VALIDATION_RE.match(head_lines[k])
                for k in range(max(0, i - 3), i)
            ):
                return None  # Head kept the validation — nothing to restore.
            head_index = i
            break
    if head_index is None:
        return None
    head_context = head_lines[head_index]
    patch = _unified_patch(
        str(finding["location"]),
        head_lines,
        head_lines[:head_index] + removed + head_lines[head_index:],
    )
    return FixProposal(
        fix_id="",
        finding_id=str(finding.get("id", "")),
        contract_id=str(finding.get("contract_id", "")),
        path=str(finding["location"]),
        action="insert_lines",
        anchor_line=head_index + 1,
        head_context=head_context,
        base_lines=removed,
        head_lines=[],
        rationale=f"Restore the removed validation annotation on field {field_name}",
        patch=patch,
    )


def propose_fixes(
    findings: list[dict[str, Any]], base_dir: Path, head_dir: Path
) -> tuple[list[FixProposal], list[dict[str, Any]]]:
    """Propose deterministic fixes; return (proposals, skipped-with-reason)."""
    base_files = _java_files(base_dir)
    head_files = _java_files(head_dir)
    proposals: list[FixProposal] = []
    skipped: list[dict[str, Any]] = []
    for finding in findings:
        contract_id = str(finding.get("contract_id", ""))
        path = finding.get("location") or finding.get("path") or ""
        if not path or path not in base_files or path not in head_files:
            skipped.append({
                "finding_id": finding.get("id"),
                "reason": "file not present in both Base and Head trees",
            })
            continue
        base_lines = _read_lines(base_files[path])
        head_lines = _read_lines(head_files[path])
        proposal: FixProposal | None = None
        if contract_id in _ANNOTATION_CONTRACTS:
            proposal = _restore_annotation(finding, base_lines, head_lines)
        elif contract_id in _TOKEN_CONTRACTS:
            proposal = _restore_token_call(finding, base_lines, head_lines)
        elif contract_id in _EVENT_CONTRACTS:
            proposal = _restore_event(finding, base_lines, head_lines)
        elif contract_id in _VALIDATION_CONTRACTS:
            proposal = _restore_validation(finding, base_lines, head_lines)
        if proposal is None:
            skipped.append({
                "finding_id": finding.get("id"),
                "contract_id": contract_id,
                "reason": (
                    "no deterministic restoration available for this "
                    "finding (anchor not found or fix not mechanical)"
                ),
            })
            continue
        proposals.append(proposal)
    final: list[FixProposal] = []
    for index, proposal in enumerate(proposals, start=1):
        final.append(FixProposal(
            fix_id=f"FIX-{proposal.contract_id}-{index:02d}",
            finding_id=proposal.finding_id,
            contract_id=proposal.contract_id,
            path=proposal.path,
            action=proposal.action,
            anchor_line=proposal.anchor_line,
            head_context=proposal.head_context,
            base_lines=proposal.base_lines,
            head_lines=proposal.head_lines,
            rationale=proposal.rationale,
            patch=proposal.patch,
        ))
    return final, skipped


def apply_fix(proposal: FixProposal, head_dir: Path) -> bool:
    """Apply one proposal to the Head tree; False on anchor drift.

    The anchor guard is the honesty gate: if the Head file no longer matches
    the line the proposal was built against, the patch is NOT applied — a
    stale patch applied blindly is worse than a reported rejection.
    """
    target = head_dir / proposal.path
    if not target.is_file():
        return False
    lines = _read_lines(target)
    index = proposal.anchor_line - 1
    if not (0 <= index < len(lines)):
        return False
    if lines[index].strip() != proposal.head_context.strip():
        return False
    if proposal.action == "insert_lines":
        new_lines = lines[:index] + proposal.base_lines + lines[index:]
    elif proposal.action == "replace_lines":
        new_lines = (
            lines[:index]
            + proposal.base_lines
            + lines[index + len(proposal.head_lines):]
        )
    elif proposal.action == "remove_lines":
        new_lines = lines[:index] + lines[index + len(proposal.head_lines):]
    else:
        return False
    target.write_text(
        "\n".join(new_lines) + ("\n" if new_lines else ""),
        encoding="utf-8",
    )
    return True


def render_fix_summary(
    proposals: list[FixProposal], skipped: list[dict[str, Any]]
) -> str:
    """Markdown summary for the CLI and the fix request file."""
    lines = [f"## Fix Requests ({len(proposals)} proposed)", ""]
    for proposal in proposals:
        lines.append(
            rf"- **{proposal.fix_id}** \`{proposal.path}:{proposal.anchor_line}\` "
            f"({proposal.action}) — {proposal.rationale}"
        )
    if skipped:
        lines.append("")
        lines.append(f"### Skipped ({len(skipped)} — no honest fix possible)")
        for item in skipped:
            lines.append(
                f"- {item.get('finding_id', '?')}: {item.get('reason', '')}"
            )
    return "\n".join(lines)
