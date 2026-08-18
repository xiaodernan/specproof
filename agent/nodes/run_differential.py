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
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, cast

from agent.contract_results import merge_contract_results
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


def run_differential_node(state: Phase0State) -> dict[str, Any]:
    """Run the generated counterexample test on Base and Head workspaces."""
    base_workspace = state.get("base_workspace", "")
    head_workspace = state.get("head_workspace", "")
    app_dir = state.get("app_dir", "")
    changed_symbols = state.get("changed_symbols", [])
    generation_record = cast(
        dict[str, Any], state.get("generation_record", {})
    )
    contracts = state.get("contracts", [])
    generated_tests_path = state.get("generated_tests_path", "")

    empty_result: dict[str, Any] = {
        "diff_results": [{
            "contract_id": "DIFF-01",
            "verdict": "NON_REPRODUCIBLE",
            "detail": "Workspace not prepared — cannot run differential execution",
        }],
        "contract_results": [],
    }
    if not base_workspace or not head_workspace:
        return empty_result

    base_app = str(Path(base_workspace) / app_dir) if app_dir else base_workspace
    head_app = str(Path(head_workspace) / app_dir) if app_dir else head_workspace

    # ── Source-level annotation diff (deterministic, MAJOR-capped) ──
    # Runs unconditionally: it depends only on the two source trees, so a
    # test-generation or Maven failure can never erase this evidence.
    source_diff_results: list[dict[str, Any]] = []
    for hd in _check_http_diff(base_app, head_app):
        source_diff_results.append({
            # Security-annotation removal is the AUTH contract family; using
            # AUTH-01 here lets the Review Court deduplicate it against the
            # static checker's finding for the same construct.
            "contract_id": "AUTH-01",
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

    test_class = _test_class_from_path(generated_tests_path)
    if not test_class:
        empty_result["diff_results"][0]["detail"] = (
            "No generated counterexample test available — nothing to run; "
            "source-diff evidence recorded separately"
        )
        # Do NOT touch contract_results: this experiment produced none.
        return {
            "diff_results": source_diff_results + empty_result["diff_results"],
        }

    # ── Inject the generated test into BOTH workspaces ──
    injected = _inject_test_into_workspaces(generated_tests_path, base_app, head_app)
    if not injected:
        empty_result["diff_results"][0]["detail"] = (
            "Could not inject generated test into both workspaces; "
            "source-diff evidence recorded separately"
        )
        return {
            "diff_results": source_diff_results + empty_result["diff_results"],
        }

    # ── Run the SAME generated test on Base and Head ──
    base_result = _run_generated_test(base_app, test_class)
    head_result = _run_generated_test(head_app, test_class)

    if base_result.get("error") or head_result.get("error"):
        err_detail = (
            f"head: {head_result.get('error') or 'ok'}, "
            f"base: {base_result.get('error') or 'ok'}"
        )
        return {
            "diff_results": source_diff_results + [{
                "contract_id": "DIFF-01",
                "verdict": "NON_REPRODUCIBLE",
                "detail": f"Maven execution error: {err_detail}",
                "base_exit_code": base_result.get("exit_code"),
                "head_exit_code": head_result.get("exit_code"),
                "changed_symbols": changed_symbols,
            }],
        }

    base_pass = base_result.get("exit_code") == 0
    head_pass = head_result.get("exit_code") == 0

    # ── Real DB state capture (file-based H2 dump) ──
    base_snapshot = _capture_db_snapshot(base_app)
    head_snapshot = _capture_db_snapshot(head_app)

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

    # Attribute the regression to the contract family the FAILING
    # generated test actually exercises (the generated class now carries
    # AUTH and UNIQUE tests; a one-size AUTH-01 label would misattribute
    # the case-17 inversion to the auth contract).
    attributed_contract = "AUTH-01"
    if base_pass and not head_pass:
        attributed_contract = _contract_for_test_method(
            _failing_test_name(head_app)
        )
    elif not base_pass and head_pass:
        attributed_contract = _contract_for_test_method(
            _failing_test_name(base_app)
        )

    diff_results: list[dict[str, Any]] = [{
        # The experiment id is DIFF-01; the CONTRACT it verified is the one
        # the failing test exercises. The Review Court requires an approved
        # contract for BLOCKER, so contract_id must match a compiled
        # contract, not the experiment label.
        "contract_id": attributed_contract,
        "experiment_id": "DIFF-01",
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

    # Source-diff findings computed earlier are prepended; the generated-test
    # verdict is the primary experiment for DIFF-01.
    diff_results = source_diff_results + diff_results

    # ── Contract results: only what this experiment exercised ──
    contract_results: list[dict[str, Any]] = []
    for c in contracts:
        cid = c.get("id", "")
        is_auth = c.get("checker_type") == "http" and cid.upper().startswith("AUTH")
        is_unique = cid == "UNIQUE-01"
        if is_auth or is_unique:
            if http_verdict == "COMPLIANT":
                result = "PASS"
            elif http_verdict == "REGRESSION" and attributed_contract == cid:
                result = "FAIL"
            else:
                result = "UNVERIFIED"
            contract_results.append({
                "contract_id": cid,
                "result": result,
                "experiment": "generated_test_differential",
                "evidence_ref": f"sha256:{evidence_digest}",
            })

    # Merge into the shared channel so static-check results for OTHER
    # contracts survive (channel values are replaced, not merged, by LangGraph).
    merged_contract_results = merge_contract_results(
        state.get("contract_results", []), contract_results
    )
    return {
        "diff_results": diff_results,
        "contract_results": merged_contract_results,
    }


def _failing_test_name(app_dir: str) -> str:
    """Return the first failing/erroring generated test method ('' when
    unavailable), parsed from the surefire XML left by the Maven run."""
    import xml.etree.ElementTree as ET

    report = Path(app_dir) / "target" / "surefire-reports" / (
        "TEST-com.specproof.demo.SpecProofGeneratedTest.xml"
    )
    try:
        root = ET.parse(report).getroot()
    except (OSError, ET.ParseError):
        return ""
    for case in root.findall("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            return case.get("name", "")
    return ""


def _contract_for_test_method(method_name: str) -> str:
    """Map a generated test method to the contract family it exercises."""
    if "unauthenticated" in method_name:
        return "AUTH-01"
    if "duplicate" in method_name or "fresh" in method_name:
        return "UNIQUE-01"
    return "AUTH-01"


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
        dest = (
            Path(ws) / "src" / "test" / "java" / "com" / "specproof" / "demo"
            / src.name
        )
        try:
            # Copying a file onto itself raises SameFileError (an OSError):
            # the head workspace already CONTAINS the generated test, so skip
            # it there instead of failing the whole injection.
            if dest.resolve() == src.resolve():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
        except OSError:
            ok = False
    return ok


def _run_generated_test(workspace: str, test_class: str) -> dict[str, Any]:
    """Run only the generated test class via Maven Surefire."""
    result: dict[str, Any] = {
        "exit_code": -1, "stdout": "", "stderr": "", "error": "",
        "test_counts": {},
    }
    pom = Path(workspace) / "pom.xml"
    if not pom.exists():
        result["error"] = "No pom.xml found"
        return result

    # P0-A1: the differential test runs inside the execution SANDBOX.
    # Untrusted test code must never execute with host privileges.
    import platform

    from sandbox.runner import run_sandboxed

    if platform.system() == "Windows":
        local_cmd = [
            os.path.join(workspace, "mvnw.cmd"), "test", "-q",
            f"-Dtest={test_class}", "-DfailIfNoTests=false",
        ]
    else:
        local_cmd = [
            os.path.join(workspace, "mvnw"), "test", "-q",
            f"-Dtest={test_class}", "-DfailIfNoTests=false",
        ]
    sandbox_result = run_sandboxed(
        [
            "mvn", "test", "-q",
            f"-Dtest={test_class}",
            "-DfailIfNoTests=false",
            "-f", "/work/pom.xml",
        ],
        workspace=workspace,
        timeout=900,
        local_command=local_cmd,
    )
    result["sandbox_mode"] = sandbox_result.mode
    if sandbox_result.error:
        result["error"] = "Sandbox execution failed: " + sandbox_result.error
        return result
    result["exit_code"] = sandbox_result.exit_code
    result["stdout"] = sandbox_result.stdout
    result["stderr"] = sandbox_result.stderr
    result["test_counts"] = _parse_test_counts(
        sandbox_result.stdout + sandbox_result.stderr
    )
    result["error"] = ""
    return result


def _parse_test_counts(output: str) -> dict[str, Any]:
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


def _capture_db_snapshot(workspace: str) -> dict[str, Any]:
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


def _compare_db_state(
    base_snapshot: dict[str, Any], head_snapshot: dict[str, Any]
) -> tuple[str, str]:
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


def _check_http_diff(base_ws: str, head_ws: str) -> list[dict[str, Any]]:
    """Compare security protection between Base and Head.

    Delegates to the SHARED AUTH checker (agent/checkers/java_source.py)
    so the equivalence rules live in exactly one place: composed custom
    annotations (@RequireAuth etc.) and interface-level method security
    are honored here exactly like in the static tier. A file-level
    "@PreAuthorize present/absent" comparison cannot see either, and
    produced false positives on the adversarial cases (13/14).
    """
    from agent.checkers.java_source import check_auth_annotations

    base_files = {
        p.relative_to(base_ws).as_posix(): p.read_text(encoding="utf-8")
        for p in Path(base_ws).rglob("*.java")
        if "test" not in p.parts
    }
    head_files = {
        p.relative_to(head_ws).as_posix(): p.read_text(encoding="utf-8")
        for p in Path(head_ws).rglob("*.java")
        if "test" not in p.parts
    }

    findings: list[dict[str, Any]] = []
    for auth_finding in check_auth_annotations(base_files, head_files):
        findings.append({
            "verdict": "REGRESSION",
            "detail": auth_finding["description"],
            "location": auth_finding["location"],
        })
    return findings


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""
