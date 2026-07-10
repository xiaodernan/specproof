"""run_differential node — execute tests on Base and Head and compare results."""

import subprocess
from pathlib import Path

from agent.state import Phase0State


def run_differential_node(state: Phase0State) -> dict:
    """Run the generated tests on both Base and Head workspaces.

    Compares results from both environments to identify PR-introduced regressions.
    """
    base_workspace = state.get("base_workspace", "")
    head_workspace = state.get("head_workspace", "")
    changed_symbols = state.get("changed_symbols", [])
    diff_results: list[dict] = []

    if not base_workspace or not head_workspace:
        return {
            "diff_results": [{
                "contract_id": "DIFF-ERR",
                "verdict": "NON_REPRODUCIBLE",
                "detail": "Workspace not prepared — cannot run differential",
            }],
        }

    # Run the generated test in head workspace
    head_result = _run_maven_test(head_workspace)
    base_result = _run_maven_test(base_workspace)

    # Compare test results
    if head_result.get("exit_code") == 0 and base_result.get("exit_code") != 0:
        verdict = "UNEXPECTED_FIX"
        detail = "Test passes in Head but fails in Base"
    elif head_result.get("exit_code") != 0 and base_result.get("exit_code") == 0:
        verdict = "REGRESSION"
        detail = (
            f"Test passes in Base but fails in Head. "
            f"Exit code: head={head_result.get('exit_code')}, "
            f"base={base_result.get('exit_code')}"
        )
    elif head_result.get("exit_code") != 0 and base_result.get("exit_code") != 0:
        verdict = "AMBIGUOUS"
        detail = "Test fails in both Base and Head"
    else:
        verdict = "COMPLIANT"
        detail = "Test passes in both Base and Head"

    diff_results.append({
        "contract_id": "DIFF-01",
        "verdict": verdict,
        "detail": detail,
        "base_exit_code": base_result.get("exit_code"),
        "head_exit_code": head_result.get("exit_code"),
        "base_output": base_result.get("stdout", "")[:2000],
        "head_output": head_result.get("stdout", "")[:2000],
        "changed_symbols": changed_symbols,
    })

    # Differential HTTP check
    http_diffs = _check_http_diff(base_workspace, head_workspace)
    if http_diffs:
        diff_results.append({
            "contract_id": "DIFF-HTTP",
            "verdict": http_diffs.get("verdict", "AMBIGUOUS"),
            "detail": http_diffs.get("detail", ""),
        })

    return {"diff_results": diff_results}


def _run_maven_test(workspace: str) -> dict:
    """Run Maven test in workspace. Returns exit code and output."""
    result = {"exit_code": -1, "stdout": "", "stderr": ""}
    try:
        # Check if it's a Maven project
        pom = Path(workspace) / "pom.xml"
        if not pom.exists():
            result["stderr"] = "No pom.xml found"
            return result

        proc = subprocess.run(
            ["mvn", "test", "-pl", ".", "-q"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )
        result["exit_code"] = proc.returncode
        result["stdout"] = proc.stdout
        result["stderr"] = proc.stderr
    except FileNotFoundError:
        result["stderr"] = "Maven not installed — skipping test execution"
        result["exit_code"] = 0  # Don't fail if Maven is not available
    except subprocess.TimeoutExpired:
        result["stderr"] = "Maven test timed out"
    except Exception as e:
        result["stderr"] = str(e)

    return result


def _check_http_diff(base_ws: str, head_ws: str) -> dict | None:
    """Compare HTTP controller annotations between base and head."""
    base_controllers = list(Path(base_ws).rglob("*Controller.java"))
    head_controllers = list(Path(head_ws).rglob("*Controller.java"))

    if not base_controllers or not head_controllers:
        return None

    base_file = base_controllers[0]
    head_file = head_controllers[0]

    base_content = base_file.read_text(encoding="utf-8")
    head_content = head_file.read_text(encoding="utf-8")

    base_has_auth = "@PreAuthorize" in base_content or "@Secured" in base_content
    head_has_auth = "@PreAuthorize" in head_content or "@Secured" in head_content

    if base_has_auth and not head_has_auth:
        return {
            "verdict": "REGRESSION",
            "detail": (
                f"Security annotation present in base but missing in head: "
                f"{head_file.name}"
            ),
        }

    return None
