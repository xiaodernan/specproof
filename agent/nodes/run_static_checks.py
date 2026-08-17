"""run_static_checks node — deterministic contract checkers on Base/Head sources.

v2: replaced the ad-hoc regex scans with the contract checker registry
(agent/checkers). Every finding carries "java_source_diff" evidence and is
capped at MAJOR by the Review Court. The node also emits per-contract
results: FAIL when a checker found a violation, PASS when the checked
construct is intact in Head, UNVERIFIED otherwise.
"""

from pathlib import Path

from agent.checkers.java_source import contract_results_for, run_contract_checks
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


def run_static_checks_node(state: Phase0State) -> dict:
    """Run deterministic contract checkers against Base and Head sources."""
    base_workspace = state.get("base_workspace", "")
    head_workspace = state.get("head_workspace", "")
    app_dir = state.get("app_dir", "")
    contracts = state.get("contracts", [])

    if not base_workspace or not head_workspace:
        return {"static_findings": [], "contract_results": []}

    base_app = str(Path(base_workspace) / app_dir) if app_dir else base_workspace
    head_app = str(Path(head_workspace) / app_dir) if app_dir else head_workspace
    base_files = _read_java_files(base_app)
    head_files = _read_java_files(head_app)

    findings = run_contract_checks(base_files, head_files)

    # Static analysis can never reach BLOCKER confidence.
    for f in findings:
        f["severity"] = "MAJOR" if f.get("severity") == "BLOCKER" else f.get("severity", "MAJOR")
        f["confidence"] = min(f.get("confidence", 0.85), _STATIC_CONFIDENCE_CEILING)
        f["p0_5_note"] = (
            "Static source-diff analysis cannot produce BLOCKER. "
            "Requires base_pass_head_fail + db_state_mutation evidence."
        )

    contract_results = contract_results_for(contracts, findings, base_files)

    return {
        "static_findings": findings,
        "contract_results": contract_results,
    }
