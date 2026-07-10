"""run_differential node — execute tests on Base and Head and compare results."""

import platform
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

    # Check for infrastructure errors
    if head_result.get("error") or base_result.get("error"):
        err_detail = (
            f"head: {head_result.get('error') or 'ok'}, "
            f"base: {base_result.get('error') or 'ok'}"
        )
        diff_results.append({
            "contract_id": "DIFF-01",
            "verdict": "NON_REPRODUCIBLE",
            "detail": f"Maven execution error: {err_detail}",
            "base_exit_code": base_result.get("exit_code"),
            "head_exit_code": head_result.get("exit_code"),
            "base_output": base_result.get("stderr", "")[:2000],
            "head_output": head_result.get("stderr", "")[:2000],
            "changed_symbols": changed_symbols,
        })
        return {"diff_results": diff_results}

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
    """Run Maven test in workspace. Tries mvnw (wrapper) then mvn (system).

    Returns dict with exit_code, stdout, stderr, and optional error.
    """
    result: dict = {"exit_code": -1, "stdout": "", "stderr": "", "error": ""}
    pom = Path(workspace) / "pom.xml"
    if not pom.exists():
        result["error"] = "No pom.xml found"
        return result

    is_windows = platform.system() == "Windows"
    mvnw_cmd = "mvnw.cmd" if is_windows else "./mvnw"
    candidates = [mvnw_cmd, "mvn"]

    for cmd in candidates:
        try:
            proc = subprocess.run(
                [cmd, "test", "-pl", ".", "-q"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=300,
            )
            result["exit_code"] = proc.returncode
            result["stdout"] = proc.stdout
            result["stderr"] = proc.stderr
            result["error"] = ""
            return result
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            result["error"] = f"Maven test timed out (cmd: {cmd})"
            return result
        except Exception as e:
            result["error"] = str(e)
            return result

    result["error"] = "Neither mvnw nor mvn found — run 'mvnw.cmd' from project root"
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
