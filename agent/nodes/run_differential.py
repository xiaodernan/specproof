"""run_differential node — execute the generated test on BOTH Base and Head.

v2 honesty fixes:
- The generated counterexample test is injected into BOTH workspaces before
  running, so "base_pass_head_fail" means what it says.
- DB state is captured by reading the file-based H2 database the test run
  left behind (via SpecProofDbCheck), never inferred from file names.
- The evidence digest is deterministic: no timestamps, so a re-run of the
  same inputs produces the same digest.
- A contract is marked PASS/FAIL only for what this experiment actually
  exercised (the HTTP/auth contract family). Everything else stays
  UNVERIFIED and is judged by other experiment nodes.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from agent.state import Phase0State

# Java source for the post-mortem DB dump helper. It opens the file-based
# H2 database that the Spring Boot test run left on disk and prints one
# "id=email" line per user row. The H2 database file persists after the
# Maven JVM exits, so this is real state inspection, not inference.
_DB_CHECK_JAVA = """
import java.sql.*;

public class SpecProofDbCheck {
    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.out.println("USAGE: SpecProofDbCheck <jdbc-url>");
            System.exit(2);
        }
        try (Connection conn = DriverManager.getConnection(args[0], "sa", "");
             Statement stmt = conn.createStatement()) {
            ResultSet rs = stmt.executeQuery(
                "SELECT id, email FROM users ORDER BY id");
            while (rs.next()) {
                System.out.println(rs.getLong("id") + "=" + rs.getString("email"));
            }
        }
    }
}
"""


def run_differential_node(state: Phase0State) -> dict:
    """Run the generated counterexample test on Base and Head workspaces."""
    base_workspace = state.get("base_workspace", "")
    head_workspace = state.get("head_workspace", "")
    changed_symbols = state.get("changed_symbols", [])
    generation_record = state.get("generation_record", {})
    contracts = state.get("contracts", [])
    generated_tests_path = state.get("generated_tests_path", "")

    empty_result: dict = {
        "diff_results": [{
            "contract_id": "DIFF-01",
            "verdict": "NON_REPRODUCIBLE",
            "detail": "Workspace not prepared — cannot run differential execution",
        }],
        "contract_results": [],
    }
    if not base_workspace or not head_workspace:
        return empty_result

    test_class = _test_class_from_path(generated_tests_path)
    if not test_class:
        empty_result["diff_results"][0]["detail"] = (
            "No generated counterexample test available — nothing to run"
        )
        return empty_result

    # ── Inject the generated test into BOTH workspaces ──
    injected = _inject_test_into_workspaces(generated_tests_path, base_workspace, head_workspace)
    if not injected:
        empty_result["diff_results"][0]["detail"] = (
            "Could not inject generated test into both workspaces"
        )
        return empty_result

    # ── Run the SAME generated test on Base and Head ──
    base_result = _run_generated_test(base_workspace, test_class)
    head_result = _run_generated_test(head_workspace, test_class)

    if base_result.get("error") or head_result.get("error"):
        err_detail = (
            f"head: {head_result.get('error') or 'ok'}, "
            f"base: {base_result.get('error') or 'ok'}"
        )
        return {
            "diff_results": [{
                "contract_id": "DIFF-01",
                "verdict": "NON_REPRODUCIBLE",
                "detail": f"Maven execution error: {err_detail}",
                "base_exit_code": base_result.get("exit_code"),
                "head_exit_code": head_result.get("exit_code"),
                "changed_symbols": changed_symbols,
            }],
            "contract_results": [],
        }

    base_pass = base_result.get("exit_code") == 0
    head_pass = head_result.get("exit_code") == 0

    # ── Real DB state capture (file-based H2 dump) ──
    base_snapshot = _capture_db_snapshot(base_workspace)
    head_snapshot = _capture_db_snapshot(head_workspace)

    # ── HTTP-level verdict ──
    if base_pass and not head_pass:
        http_verdict = "REGRESSION"
        http_detail = (
            f"Test passes in Base (exit 0) but fails in Head "
            f"(exit {head_result.get('exit_code')})"
        )
    elif base_pass and head_pass:
        http_verdict = "COMPLIANT"
        http_detail = "Test passes in both Base and Head"
    elif not base_pass and not head_pass:
        http_verdict = "AMBIGUOUS"
        http_detail = "Test fails in both Base and Head"
    else:
        http_verdict = "UNEXPECTED_FIX"
        http_detail = (
            f"Test fails in Base (exit {base_result.get('exit_code')}) "
            "but passes in Head"
        )

    # ── DB state comparison ──
    db_verdict, db_detail = _compare_db_state(base_snapshot, head_snapshot)

    # ── Combined verdict ──
    if http_verdict == "REGRESSION" and db_verdict == "DB_MUTATED_ON_UNAUTH":
        combined_verdict = "REGRESSION"
        combined_detail = (
            f"{http_detail}. {db_detail}. "
            "Base blocked the unauthenticated write and kept the row intact; "
            "Head accepted it and mutated the row."
        )
        combined_confidence = 0.95
        combined_severity = "BLOCKER"
    elif http_verdict == "REGRESSION":
        combined_verdict = "REGRESSION"
        combined_detail = (
            f"{http_detail}. DB evidence: {db_detail}. "
            "HTTP regression confirmed; DB mutation not directly captured."
        )
        combined_confidence = 0.88
        combined_severity = "MAJOR"
    else:
        combined_verdict = http_verdict
        combined_detail = http_detail
        combined_confidence = 0.80
        combined_severity = "NONE"

    # ── Deterministic evidence digest (no timestamps) ──
    test_sha = _sha256_file(Path(generated_tests_path)) if generated_tests_path else ""
    evidence_payload = json.dumps({
        "verdict": combined_verdict,
        "base_exit": base_result.get("exit_code"),
        "head_exit": head_result.get("exit_code"),
        "base_db_rows": base_snapshot.get("rows", {}),
        "head_db_rows": head_snapshot.get("rows", {}),
        "base_test_counts": base_result.get("test_counts", {}),
        "head_test_counts": head_result.get("test_counts", {}),
        "test_file_sha256": test_sha,
    }, sort_keys=True)
    evidence_digest = hashlib.sha256(evidence_payload.encode()).hexdigest()

    diff_results: list[dict] = [{
        "contract_id": "DIFF-01",
        "verdict": combined_verdict,
        "detail": combined_detail,
        "severity": combined_severity,
        "confidence": combined_confidence,
        "evidence_type": (
            "base_pass_head_fail" if combined_verdict == "REGRESSION"
            else "differential_execution"
        ),
        "base_exit_code": base_result.get("exit_code"),
        "head_exit_code": head_result.get("exit_code"),
        "base_test_counts": base_result.get("test_counts", {}),
        "head_test_counts": head_result.get("test_counts", {}),
        "base_output": (base_result.get("stdout", "") + base_result.get("stderr", ""))[:2000],
        "head_output": (head_result.get("stdout", "") + head_result.get("stderr", ""))[:2000],
        "base_db_snapshot": base_snapshot,
        "head_db_snapshot": head_snapshot,
        "db_state_verdict": db_verdict,
        "db_state_detail": db_detail,
        "evidence_digest": f"sha256:{evidence_digest}",
        "test_file_sha256": test_sha,
        "changed_symbols": changed_symbols,
        "generation_source": generation_record.get("source", "unknown"),
    }]

    # ── Source-level annotation diff (deterministic, MAJOR-capped) ──
    http_diffs = _check_http_diff(base_workspace, head_workspace)
    for hd in http_diffs:
        diff_results.append({
            "contract_id": "DIFF-HTTP",
            "verdict": hd.get("verdict", "AMBIGUOUS"),
            "detail": hd.get("detail", ""),
            "evidence_type": "java_source_diff",
            "location": hd.get("location", ""),
            "severity": "MAJOR",
            "confidence": 0.85,
            "evidence_digest": (
                "sha256:"
                + hashlib.sha256(
                    json.dumps(hd, sort_keys=True).encode()
                ).hexdigest()
            ),
        })

    # ── Contract results: only what this experiment exercised ──
    contract_results: list[dict] = []
    for c in contracts:
        cid = c.get("id", "")
        if c.get("checker_type") == "http" and cid.upper().startswith("AUTH"):
            if http_verdict == "COMPLIANT":
                result = "PASS"
            elif http_verdict == "REGRESSION":
                result = "FAIL"
            else:
                result = "UNVERIFIED"
            contract_results.append({
                "contract_id": cid,
                "result": result,
                "experiment": "generated_test_differential",
                "evidence_ref": f"sha256:{evidence_digest}",
            })

    return {"diff_results": diff_results, "contract_results": contract_results}


def _test_class_from_path(test_path: str) -> str:
    """Derive the JUnit class name from the generated test file path."""
    if not test_path:
        return ""
    name = Path(test_path).name
    if name.endswith(".java"):
        name = name[:-5]
    if not name:
        return ""
    return name


def _inject_test_into_workspaces(test_path: str, base_ws: str, head_ws: str) -> bool:
    """Copy the generated test into the test tree of BOTH workspaces."""
    src = Path(test_path)
    if not src.exists():
        return False
    ok = True
    for ws in (base_ws, head_ws):
        dest_dir = (
            Path(ws) / "src" / "test" / "java" / "com" / "specproof" / "demo"
        )
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest_dir / src.name))
        except OSError:
            ok = False
    return ok


def _run_generated_test(workspace: str, test_class: str) -> dict:
    """Run only the generated test class via Maven Surefire."""
    result: dict = {
        "exit_code": -1, "stdout": "", "stderr": "", "error": "",
        "test_counts": {},
    }
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
                [cmd, "test", "-q",
                 f"-Dtest={test_class}",
                 "-DfailIfNoTests=false"],
                cwd=workspace,
                capture_output=True, text=True, timeout=600,
            )
            result["exit_code"] = proc.returncode
            result["stdout"] = proc.stdout
            result["stderr"] = proc.stderr
            result["test_counts"] = _parse_test_counts(proc.stdout + proc.stderr)
            result["error"] = ""
            return result
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            result["error"] = f"Maven test timed out (cmd: {cmd})"
            return result
        except Exception as e:  # noqa: BLE001
            result["error"] = str(e)
            return result

    result["error"] = "Neither mvnw nor mvn found"
    return result


def _parse_test_counts(output: str) -> dict:
    m = re.search(
        r"Tests run:\s*(\d+).*?Failures:\s*(\d+).*?Errors:\s*(\d+).*?Skipped:\s*(\d+)",
        output,
        re.DOTALL,
    )
    if m:
        return {
            "tests": int(m.group(1)),
            "failures": int(m.group(2)),
            "errors": int(m.group(3)),
            "skipped": int(m.group(4)),
        }
    return {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}


def _h2_db_file(workspace: str) -> Path | None:
    """Locate the file-based H2 database the test run left behind."""
    candidates = [
        Path(workspace) / "target" / "h2" / "specproof-test.mv.db",
        Path(workspace) / "data" / "specproof-test.mv.db",
        Path(workspace) / "specproof-test.mv.db",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _find_h2_jar() -> Path | None:
    """Find the H2 JDBC jar in the local Maven repository."""
    m2 = Path.home() / ".m2" / "repository" / "com" / "h2database" / "h2"
    if not m2.exists():
        return None
    jars = sorted(m2.glob("*/h2-*.jar"), reverse=True)
    return jars[0] if jars else None


def _capture_db_snapshot(workspace: str) -> dict:
    """Capture the real database state left behind by the test run."""
    db_file = _h2_db_file(workspace)
    if db_file is None:
        return {
            "method": "none",
            "rows": {},
            "note": "No file-based H2 database found after test run. "
                    "Switch the test profile to file-based H2 to capture DB state.",
        }
    h2_jar = _find_h2_jar()
    if h2_jar is None:
        return {
            "method": "none",
            "rows": {},
            "note": "H2 jar not found in local Maven repository.",
        }

    jdbc_url = "jdbc:h2:file:" + str(db_file).replace(".mv.db", "")
    with tempfile.TemporaryDirectory(prefix="specproof-dbcheck-") as tmp:
        src = Path(tmp) / "SpecProofDbCheck.java"
        src.write_text(_DB_CHECK_JAVA, encoding="utf-8")
        classpath = str(h2_jar) + os.pathsep + tmp
        try:
            javac = subprocess.run(
                ["javac", "-cp", str(h2_jar), str(src)],
                capture_output=True, text=True, timeout=60,
            )
            if javac.returncode != 0:
                return {
                    "method": "none", "rows": {},
                    "note": f"SpecProofDbCheck compile failed: {javac.stderr[:200]}",
                }
            run = subprocess.run(
                ["java", "-cp", classpath, "SpecProofDbCheck", jdbc_url],
                capture_output=True, text=True, timeout=60,
            )
            if run.returncode != 0:
                return {
                    "method": "none", "rows": {},
                    "note": f"SpecProofDbCheck run failed: {run.stderr[:200]}",
                }
            rows: dict[str, str] = {}
            for line in run.stdout.splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    rows[k.strip()] = v.strip()
            return {
                "method": "h2_file_dump",
                "rows": rows,
                "db_file": str(db_file),
                "note": "",
            }
        except Exception as e:  # noqa: BLE001
            return {"method": "none", "rows": {}, "note": str(e)}


def _compare_db_state(base_snapshot: dict, head_snapshot: dict) -> tuple[str, str]:
    """Compare the real DB dumps from Base and Head.

    Returns (verdict, detail):
    - DB_MUTATED_ON_UNAUTH: same row changed between Base and Head.
    - DB_CONSISTENT: identical rows.
    - DB_NO_EVIDENCE: no dump available.
    - DB_DIFFERENT: rows differ in an unexpected way.
    """
    base_method = base_snapshot.get("method")
    head_method = head_snapshot.get("method")
    if base_method != "h2_file_dump" or head_method != "h2_file_dump":
        note = base_snapshot.get("note") or head_snapshot.get("note")
        return "DB_NO_EVIDENCE", f"No H2 dump available: {note}"

    base_rows = base_snapshot.get("rows", {})
    head_rows = head_snapshot.get("rows", {})
    if base_rows == head_rows:
        return "DB_CONSISTENT", "Base and Head DB dumps are identical"

    changed: list[str] = []
    for key in base_rows:
        if key in head_rows and base_rows[key] != head_rows[key]:
            changed.append(f"row {key}: '{base_rows[key]}' -> '{head_rows[key]}'")
    if changed:
        return (
            "DB_MUTATED_ON_UNAUTH",
            "Real H2 dump comparison — " + "; ".join(changed),
        )
    return "DB_DIFFERENT", f"Rows differ: base={base_rows}, head={head_rows}"


def _check_http_diff(base_ws: str, head_ws: str) -> list[dict]:
    """Compare every controller file between Base and Head."""
    base_controllers = {
        p.relative_to(base_ws).as_posix(): p.read_text(encoding="utf-8")
        for p in Path(base_ws).rglob("*Controller.java")
        if "test" not in p.parts
    }
    head_controllers = {
        p.relative_to(head_ws).as_posix(): p.read_text(encoding="utf-8")
        for p in Path(head_ws).rglob("*Controller.java")
        if "test" not in p.parts
    }

    findings: list[dict] = []
    for rel in sorted(set(base_controllers) & set(head_controllers)):
        base_content = base_controllers[rel]
        head_content = head_controllers[rel]

        base_auth = "@PreAuthorize" in base_content or "@Secured" in base_content
        head_auth = "@PreAuthorize" in head_content or "@Secured" in head_content

        if base_auth and not head_auth:
            findings.append({
                "verdict": "REGRESSION",
                "detail": (
                    f"Security annotation present in Base ({rel}) "
                    f"but missing in Head"
                ),
                "location": rel,
            })

    return findings


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
