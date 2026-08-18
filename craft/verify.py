"""SpecCraft M3 self-verify layer (SPECCRAFT_PLAN §4.5, GRAND_PLAN_V2 卷 III M3).

The hard gate that runs after the plan/execute/verify loop and before the
report is written: craft never delivers a change that fails it. Every call
here is READ-ONLY — no file writes, no command execution, no LLM.

Layers, per changed file:
 1. security scan — reuses agent.security_scanner.scan_directory (public,
    read-only), filtered to the changed files, plus a canary-sentinel check
    on every changed file (the scanner deliberately skips canary matches,
    so the sentinel check is performed here);
 2. Java contract checkers — reuses the agent.checkers family registry
    (run_contract_checks) read-only. Base snapshots come from the Editor
    backups when provided via base_files; the diff checkers have nothing to
    observe without a Base, so files without one are reported honestly;
 3. every other file kind skips the contract checkers with a note.

Honesty contract (never faked):
 - any blocking finding (CRITICAL/HIGH secret leak, canary sentinel, or any
   Java contract-checker finding) -> status="failed" + the findings list;
 - the security scanner or the Java checker layer unavailable/error while
   there is something to check -> status="skipped" + the reason;
 - all applicable layers green -> status="passed".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.checkers.java_source import run_contract_checks  # noqa: F401
    from agent.security_scanner import scan_directory  # noqa: F401

# Sentinel shared by convention with agent/security_scanner's canary
# self-test; a changed file carrying it is a planted-secret leak.
CANARY_MARKER = "SPECPROOF_CANARY_"
BLOCKING_SECRET_SEVERITIES = ("CRITICAL", "HIGH")
JAVA_SUFFIX = ".java"


def _read_changed(workspace: Path, rel_path: str) -> str | None:
    """Read one changed file as UTF-8 text; None when unreadable/deleted."""
    target = workspace / rel_path
    try:
        return target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _secret_finding(entry: Any) -> dict[str, Any]:
    return {
        "file": str(entry.path),
        "line": int(entry.line),
        "kind": "secret",
        "severity": str(entry.severity),
        "pattern": str(entry.pattern_name),
        "description": f"{entry.pattern_name} (命中已脱敏: {entry.matched_text})",
    }


def _contract_finding(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": str(entry.get("location") or ""),
        "line": None,
        "kind": "contract",
        "severity": str(entry.get("severity") or "MAJOR"),
        "pattern": str(entry.get("contract_id") or ""),
        "description": str(entry.get("description") or ""),
    }


def self_verify(
    changed_files: Iterable[str] | None,
    workspace: str | Path,
    *,
    base_files: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run the M3 self-verify gate over the changed files of a craft run.

    Returns {"status": "passed"|"failed"|"skipped", "findings": [...], "note":
    "..."} — the exact shape written to report.self_verify. Never raises for
    checker/scanner problems: those degrade to status="skipped" + reason.
    """
    workspace_path = Path(workspace)
    changed = sorted({str(rel) for rel in changed_files or []})
    base_map = dict(base_files or {})
    findings: list[dict[str, Any]] = []
    notes: list[str] = []
    blocking: list[dict[str, Any]] = []
    gate_incomplete = False

    if not changed:
        return {
            "status": "skipped",
            "findings": [],
            "note": "无改动文件 (无编辑审计记录), 自校验无对象, 按 skipped 处理",
        }

    # -- layer 1: security scan (public scanner, read-only) -----------------

    try:
        from agent.security_scanner import scan_directory
    except Exception as exc:
        return {
            "status": "skipped",
            "findings": [],
            "note": f"安全扫描不可用 (agent.security_scanner 导入失败): {exc}",
        }
    try:
        scan_result = scan_directory(str(workspace_path))
    except Exception as exc:
        return {
            "status": "skipped",
            "findings": [],
            "note": f"安全扫描执行失败: {exc}",
        }
    changed_set = set(changed)
    for entry in scan_result.findings:
        if entry.path not in changed_set:
            continue
        finding = _secret_finding(entry)
        findings.append(finding)
        if finding["severity"] in BLOCKING_SECRET_SEVERITIES:
            blocking.append(finding)

    # Canary sentinel per changed file: scan_directory skips canary matches
    # by design (its own self-test file would trip), so the leak gate for the
    # sentinel is an explicit per-file check here.
    for rel in changed:
        content = _read_changed(workspace_path, rel)
        if content is None:
            notes.append(f"{rel}: 不可读或已删除, 跳过内容检查")
            continue
        if CANARY_MARKER in content:
            line = next(
                (
                    number
                    for number, text in enumerate(content.splitlines(), 1)
                    if CANARY_MARKER in text
                ),
                1,
            )
            finding = {
                "file": rel,
                "line": line,
                "kind": "canary",
                "severity": "CRITICAL",
                "pattern": "Canary secret",
                "description": (
                    "canary 哨兵字符串出现在改动文件 (SPECPROOF_CANARY_...): "
                    "测试哨兵泄漏, 禁止交付"
                ),
            }
            findings.append(finding)
            blocking.append(finding)

    # -- layer 2: Java contract checkers (public registry, read-only) --------

    java_files = [rel for rel in changed if rel.lower().endswith(JAVA_SUFFIX)]
    if java_files:
        try:
            from agent.checkers import run_contract_checks
        except Exception as exc:
            gate_incomplete = True
            notes.append(f"Java 契约检查器不可用 (agent.checkers 导入失败): {exc}")
        else:
            head_files: dict[str, str] = {}
            for rel in java_files:
                content = _read_changed(workspace_path, rel)
                if content is None:
                    notes.append(f"{rel}: Java 契约检查跳过 (不可读或已删除)")
                    continue
                head_files[rel] = content
            check_base = {rel: base_map[rel] for rel in head_files if rel in base_map}
            missing_base = [rel for rel in head_files if rel not in base_map]
            if missing_base:
                notes.append(
                    "Java 契约检查: 无 Base 快照 (编辑器备份), diff 检查器对这些文件 "
                    f"无可观察对象: {', '.join(sorted(missing_base))}"
                )
            if check_base:
                try:
                    contract_findings = run_contract_checks(check_base, head_files)
                except Exception as exc:
                    gate_incomplete = True
                    notes.append(f"Java 契约检查器抛错 (不伪造, 按 skipped 处理): {exc}")
                else:
                    notes.append(
                        f"Java 契约检查已运行 (checker 家族, 只读): "
                        f"{len(contract_findings)} findings / {len(check_base)} 文件"
                    )
                    for contract_entry in contract_findings:
                        finding = _contract_finding(contract_entry)
                        findings.append(finding)
                        blocking.append(finding)
            else:
                gate_incomplete = True
                notes.append(
                    "Java 契约检查: 全部 Java 改动文件均无 Base 快照, "
                    "diff 检查器无可观察对象, 不伪造通过"
                )
    else:
        notes.append("无 Java 改动文件, 契约检查器不适用")

    # -- verdict --------------------------------------------------------------

    if blocking:
        status = "failed"
        notes.append(
            f"自校验失败: {len(blocking)} 项硬门 finding "
            "(密钥/哨兵/契约回归), 交付被拦截"
        )
    elif gate_incomplete:
        status = "skipped"
        notes.append("自校验层不完整 (安全扫描或契约检查未完成), 不伪造通过")
    else:
        status = "passed"
        notes.append(
            f"自校验通过: 密钥/canary 扫描与契约检查未发现硬门 finding "
            f"(改动文件 {len(changed)} 个)"
        )
    return {
        "status": status,
        "findings": findings,
        "note": "; ".join(note for note in notes if note),
    }
