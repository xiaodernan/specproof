
"""run_static_checks node — deterministic contract checkers on Base/Head sources.

v2: replaced the ad-hoc regex scans with the contract checker registry
(agent/checkers). Every finding carries "java_source_diff" evidence and is
capped at MAJOR by the Review Court. The node also emits per-contract
results: FAIL when a checker found a violation, PASS when the checked
construct is intact in Head, UNVERIFIED otherwise.

All ten checkers are dispatched through the registry: the seven uniform
java-source checkers via run_registered_checks, and the three
heterogeneous ones (schema.sql / test-strength / forbidden changes) via
dispatch_checker by name — unknown checker names fail closed.
"""
import hashlib
import json
from pathlib import Path
from typing import Any

from agent.checkers.java_source import contract_results_for, run_contract_checks
from agent.checkers.registry import dispatch_checker
from agent.contract_results import merge_contract_results
from agent.state import Phase0State

_STATIC_CONFIDENCE_CEILING = 0.85


def _read_java_files(workspace: str) -> dict[str, str]:
    """Read src/main Java files keyed by posix relative path."""
    root = Path(workspace) / "src" / "main" / "java"
    files: dict[str, str] = {}
    if not root.exists():
        return files
    for p in root.rglob("*.java"):
        try:
            files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
        except OSError:
            continue
    return files


def _read_test_files(workspace: str) -> dict[str, str]:
    """Read src/test Java files keyed by posix relative path."""
    root = Path(workspace) / "src" / "test" / "java"
    files: dict[str, str] = {}
    if not root.exists():
        return files
    for p in root.rglob("*.java"):
        try:
            files[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
        except OSError:
            continue
    return files


def _read_text(workspace: str, rel: str) -> str:
    """Read a text resource ('' when absent)."""
    path = Path(workspace) / rel
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def run_static_checks_node(state: Phase0State) -> dict[str, Any]:
    """Run deterministic contract checkers against Base and Head sources."""
    base_workspace = state.get("base_workspace", "")
    head_workspace = state.get("head_workspace", "")
    app_dir = state.get("app_dir", "")
    contracts = state.get("contracts", [])

    if not base_workspace or not head_workspace:
        return {
            "static_findings": [],
            "contract_results": state.get("contract_results", []),
        }

    base_app = str(Path(base_workspace) / app_dir) if app_dir else base_workspace
    head_app = str(Path(head_workspace) / app_dir) if app_dir else head_workspace
    base_files = _read_java_files(base_app)
    head_files = _read_java_files(head_app)
    # Read each tree once. All checkers and the evidence digest must describe
    # the same snapshots, including schema and test-strength inputs.
    base_schema = _read_text(base_app, "src/main/resources/schema.sql")
    head_schema = _read_text(head_app, "src/main/resources/schema.sql")
    base_tests = _read_test_files(base_app)
    head_tests = _read_test_files(head_app)

    findings = run_contract_checks(base_files, head_files)

    # P6: schema/DDL and test-strength checkers operate on inputs the
    # uniform java-source registry does not see (schema.sql + test
    # sources). They are dispatched through the registry by name: an
    # unknown checker name fails closed instead of running zero checks.
    findings.extend(dispatch_checker(
        "check_schema_sql",
        base_schema=base_schema,
        head_schema=head_schema,
        base_files=base_files,
        head_files=head_files,
    ))
    findings.extend(dispatch_checker(
        "check_test_weakening",
        base_test_files=base_tests,
        head_test_files=head_tests,
    ))

    # P2-b: constitution checks — "forbidden changes" clauses from the
    # requirement run as deterministic diff rules under their own contract.
    for contract in contracts:
        clauses = contract.get("forbidden_changes", [])
        if clauses:
            findings.extend(
                dispatch_checker(
                    "check_forbidden_changes",
                    base_files=base_files,
                    head_files=head_files,
                    forbidden_clauses=clauses,
                    contract_id=contract.get("id", "CONST"),
                )
            )

    # Static analysis can never reach BLOCKER confidence. CHECKER_FAILED
    # evidence is exempt: it is infrastructure evidence, not a source verdict.
    checker_failures = [
        f for f in findings if f.get("type") == "checker_failed"
    ]
    for f in findings:
        if f.get("type") == "checker_failed":
            continue
        f["severity"] = "MAJOR" if f.get("severity") == "BLOCKER" else f.get("severity", "MAJOR")
        f["confidence"] = min(f.get("confidence", 0.85), _STATIC_CONFIDENCE_CEILING)
        f["p0_5_note"] = (
            "Static source-diff analysis cannot produce BLOCKER. "
            "Requires base_pass_head_fail + db_state_mutation evidence."
        )

    new_contract_results = contract_results_for(
        contracts,
        findings,
        base_files,
        base_schema_present=bool(base_schema),
        base_test_present=bool(base_tests),
    )
    snapshot_digest = hashlib.sha256(json.dumps({
        "base": base_files, "head": head_files,
        "base_schema": base_schema, "head_schema": head_schema,
        "base_tests": base_tests, "head_tests": head_tests,
        "contracts": contracts,
    }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    removed_sources = sorted(set(base_files) - set(head_files))
    for result in new_contract_results:
        if result["result"] != "PASS":
            continue
        if removed_sources:
            # Several legacy checkers compare only files present on both sides.
            # Their silence on deleted classes cannot prove preserved behavior.
            result["result"] = "UNVERIFIED"
            result["evidence_ref"] = None
            result["details"] = (
                "Java 源文件被删除，静态检查无法确认行为保持；请执行运行时验收: "
                + ", ".join(removed_sources)
            )
        else:
            result["evidence_ref"] = f"static:{result['contract_id']}:{snapshot_digest}"
            result["details"] = (
                "Static checker found no guarded-source regression; "
                "snapshot digest identifies its exact inputs, not runtime behavior."
            )

    # Merge with results already recorded by other experiment nodes.
    # A node must never REPLACE the whole channel: that would wipe evidence
    # other experiments produced, turning real PASS/FAIL into UNVERIFIED.
    contract_results = merge_contract_results(
        state.get("contract_results", []), new_contract_results
    )

    out: dict[str, Any] = {
        "static_findings": findings,
        "contract_results": contract_results,
    }
    if checker_failures:
        out["checker_failures"] = checker_failures
    return out
