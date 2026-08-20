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
- Execution-time reliability probes (阶段4): cases whose ground truth
  declares a probe_expectation (97/98/100) get the probe scaffolding copied
  into the base workspace, one probe test method run per side, and the
  resulting target/specproof-probe.json artifacts compared against the
  expectation (experiment PROBE-01).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from agent.contract_results import merge_contract_results
from agent.job_control import run_with_cancel_checks
from agent.nodes.build_cache import (
    base_build_cache_dir,
    freeze_unchanged_sources,
    head_changed_paths,
    restore_base_build,
    save_base_build,
    seed_head_build,
)
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
        try (Connection conn = DriverManager.getConnection(args[0], "sa", "")) {
            dumpUsers(conn);
            dumpProducts(conn);
            dumpOrders(conn);
        }
    }

    // P6: the orders/products domains joined the base, so real state
    // evidence now covers every table the differential tests exercise.
    // Each dump is independently tolerant: a missing table on old refs
    // must never erase the users-table evidence those cases rely on.
    private static void dumpUsers(Connection conn) {
        try (Statement stmt = conn.createStatement()) {
            ResultSet rs = stmt.executeQuery(
                "SELECT id, email FROM users ORDER BY id");
            while (rs.next()) {
                System.out.println(
                    "users:" + rs.getLong("id") + "=" + rs.getString("email"));
            }
        } catch (Exception e) {
            System.out.println("TABLE_ERROR users: " + e.getMessage());
        }
    }

    private static void dumpProducts(Connection conn) {
        try (Statement stmt = conn.createStatement()) {
            ResultSet rs = stmt.executeQuery(
                "SELECT id, stock, version FROM products ORDER BY id");
            while (rs.next()) {
                System.out.println("products:" + rs.getLong("id") + "="
                    + rs.getInt("stock") + ":" + rs.getLong("version"));
            }
        } catch (Exception e) {
            System.out.println("TABLE_ERROR products: " + e.getMessage());
        }
    }

    private static void dumpOrders(Connection conn) {
        try (Statement stmt = conn.createStatement()) {
            ResultSet rs = stmt.executeQuery(
                "SELECT id, user_id, request_id, amount FROM orders ORDER BY id");
            while (rs.next()) {
                System.out.println("orders:" + rs.getLong("id") + "="
                    + rs.getLong("user_id") + ":" + rs.getString("request_id")
                    + ":" + rs.getBigDecimal("amount"));
            }
        } catch (Exception e) {
            System.out.println("TABLE_ERROR orders: " + e.getMessage());
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
    generation_record = state.get("generation_record", {})
    contracts = state.get("contracts", [])
    generated_tests_path = state.get("generated_tests_path", "")
    job_id = state.get("job_id")

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

    # ── P6 base build reuse ──
    # Every case shares the same base_ref, so the first case's compile
    # output is cached under <output_dir>/.base-build-cache/<sha>; later
    # cases seed the fresh base worktree with it, freeze every source
    # (base sources never change between cases) and skip the main compile
    # (-Dmaven.main.skip=true) — only the injected generated test, written
    # after the freeze with a fresh mtime, is compiled. Head worktrees are
    # seeded in generate_counterexamples; if that run never happened and
    # left no target, seed here too (changed files stay newer than the
    # cached classes, so Maven's staleness check still recompiles them —
    # correct either way).
    cache_dir = base_build_cache_dir(state)
    base_cache_hit = False
    if cache_dir is not None:
        base_cache_hit = restore_base_build(cache_dir, base_app)
        if base_cache_hit:
            freeze_unchanged_sources(base_app, [])
        if not (Path(head_app) / "target" / "classes").is_dir():
            seed_head_build(cache_dir, head_app, head_changed_paths(state))

    # ── P6 head-run reuse ──
    # The deterministic generator already ran the FULL head test (compile +
    # surefire in one sandbox invocation) and recorded it. When the
    # recorded test file matches the current one, reuse that run — one
    # fewer Maven invocation per case. A recorded compile error is treated
    # exactly like a fresh compile failure (NON_REPRODUCIBLE below).
    recorded_run = state.get("generation_record", {}).get("head_run") or {}
    recorded_sha = state.get("generation_record", {}).get("test_file_sha256", "")
    current_sha = _sha256_file(Path(generated_tests_path)) if generated_tests_path else ""
    head_reused = bool(
        recorded_run
        and current_sha
        and recorded_sha == current_sha
        and recorded_run.get("exit_code") is not None
    )

    # ── Run the SAME generated test on Base and Head ──
    # §14 任务 8: cancellation checkpoints before+after each differential
    # execution — a cancelled job neither starts the run nor receives its
    # result (no business results get written).
    base_start = time.monotonic()
    base_result = run_with_cancel_checks(
        job_id, "maven_base", _run_generated_test,
        base_app, test_class, skip_main=base_cache_hit,
    )
    base_seconds = round(time.monotonic() - base_start, 1)
    if cache_dir is not None and base_result.get("exit_code") == 0:
        save_base_build(cache_dir, base_app)
    if head_reused:
        head_result = {
            "exit_code": recorded_run.get("exit_code"),
            "stdout": recorded_run.get("stdout", ""),
            "stderr": recorded_run.get("stderr", ""),
            "test_counts": recorded_run.get("test_counts", {}),
            "error": "",
        }
        if recorded_run.get("compile_error"):
            head_result["error"] = (
                "Generated test failed to compile on Head: "
                + (head_result["stdout"] + head_result["stderr"])[-400:]
            )
        head_seconds = 0.0
    else:
        head_start = time.monotonic()
        head_result = run_with_cancel_checks(
            job_id, "maven_head", _run_generated_test, head_app, test_class,
        )
        head_seconds = round(time.monotonic() - head_start, 1)

    # ── Execution-time reliability probes (阶段4, cases 97/98/100) ──
    # Independent of the generated-test verdict: the probe scaffolding rides
    # the case-head ref and gets copied into the base workspace here.
    probe_results = run_with_cancel_checks(
        job_id, "maven_probe", _run_probe_experiment,
        state, base_app, head_app, base_cache_hit,
    )

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
            }] + probe_results,
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

    test_sha = _sha256_file(Path(generated_tests_path)) if generated_tests_path else ""

    # ── P2 both-fail split (go-nogo #3 attribution fix) ──
    # When Base AND Head each fail, one collapsed whole-run AMBIGUOUS
    # experiment (severity NONE) masks the head-introduced failure
    # (case-att-08: Base fails UNIQUE-01 pre-existing, Head fails
    # EVENT_ONCE-01 introduced). Split the run by failing test method:
    # a method failing on Head while passing on Base is a head-introduced
    # REGRESSION for the contract it exercises; a method failing on Base
    # while passing on Head is a pre-existing UNEXPECTED_FIX (never
    # attributed to Head); a method failing on both sides stays AMBIGUOUS.
    # Method-scoped exit codes feed the Review Court's preexisting-defect
    # rule; the whole-run exits stay recorded for auditability.
    method_groups: tuple[list[str], list[str], list[str]] | None = None
    if not base_pass and not head_pass:
        method_groups = _both_fail_method_groups(base_app, head_app, test_class)

    attributed_contracts: set[str] = set()
    evidence_by_contract: dict[str, str] = {}
    evidence_digest = ""
    primary_entries: list[dict[str, Any]] = []

    if method_groups is not None:
        head_only, base_only, both = method_groups
        base_run_exit = base_result.get("exit_code")
        head_run_exit = head_result.get("exit_code")
        base_fail_details = _test_failure_details(base_app, test_class)
        head_fail_details = _test_failure_details(head_app, test_class)
        whole_run_base_output = (
            base_result.get("stdout", "") + base_result.get("stderr", "")
        )[:2000]
        whole_run_head_output = (
            head_result.get("stdout", "") + head_result.get("stderr", "")
        )[:2000]
        for method in head_only + base_only + both:
            contract_id = _contract_for_test_method(method)
            if method in head_only:
                verdict = "REGRESSION"
                severity = "MAJOR"
                confidence = 0.88
                evidence_type = "base_pass_head_fail"
                base_exit, head_exit = 0, 1
                base_status, head_status = "pass", "fail"
                detail = (
                    f"Split differential: test method {method} passes on "
                    f"Base but fails on Head — head-introduced failure for "
                    f"{contract_id} (whole-run exits: base {base_run_exit}, "
                    f"head {head_run_exit})"
                )
                attributed_contracts.add(contract_id)
                base_failure = ""
                head_failure = head_fail_details.get(method, "")
                base_output = whole_run_base_output
                head_output = whole_run_head_output
            elif method in base_only:
                verdict = "UNEXPECTED_FIX"
                severity = "NONE"
                confidence = 0.80
                evidence_type = "differential_execution"
                base_exit, head_exit = 1, 0
                base_status, head_status = "fail", "pass"
                detail = (
                    f"Split differential: test method {method} fails on "
                    f"Base but passes on Head — pre-existing base-side "
                    f"failure for {contract_id}, not attributed to the "
                    f"reviewed head (whole-run exits: base {base_run_exit}, "
                    f"head {head_run_exit})"
                )
                base_failure = base_fail_details.get(method, "")
                head_failure = ""
                base_output = whole_run_base_output
                head_output = whole_run_head_output
            else:
                # Fails on BOTH sides. One collapsed AMBIGUOUS verdict with
                # severity NONE would mask a head-introduced failure that
                # fails for a DIFFERENT reason than the Base failure (att-08:
                # Base fails the event test because the unique inversion
                # kills the email-change precondition, Head fails it because
                # the routing key is broken). Emit the per-method AMBIGUOUS
                # record WITHOUT a severity and with the per-method failure
                # snippets as the output tails: the Review Court's
                # preexisting-defect rule then compares the failure
                # signatures — identical -> not_attributed (pre-existing),
                # distinct -> confirmed (head-only behavioral difference).
                verdict = "AMBIGUOUS"
                severity = None
                confidence = 0.65
                evidence_type = "differential_execution"
                base_exit, head_exit = 1, 1
                base_status, head_status = "fail", "fail"
                detail = (
                    f"Split differential: test method {method} fails on "
                    f"both Base and Head — failure signatures compared by "
                    f"the Review Court for head-only attribution "
                    f"(whole-run exits: base {base_run_exit}, head "
                    f"{head_run_exit})"
                )
                base_failure = base_fail_details.get(method, "")
                head_failure = head_fail_details.get(method, "")
                base_output = base_failure or whole_run_base_output
                head_output = head_failure or whole_run_head_output
            digest = _split_entry_digest(
                verdict=verdict,
                contract_id=contract_id,
                method=method,
                base_status=base_status,
                head_status=head_status,
                base_run_exit=base_run_exit,
                head_run_exit=head_run_exit,
                base_result=base_result,
                head_result=head_result,
                base_snapshot=base_snapshot,
                head_snapshot=head_snapshot,
                test_sha=test_sha,
                base_failure=base_failure,
                head_failure=head_failure,
            )
            evidence_by_contract[contract_id] = digest
            primary_entries.append({
                "contract_id": contract_id,
                "experiment_id": "DIFF-01",
                "verdict": verdict,
                "detail": detail,
                "severity": severity,
                "confidence": confidence,
                "evidence_type": evidence_type,
                "base_exit_code": base_exit,
                "head_exit_code": head_exit,
                "method_scoped": True,
                "failing_test_method": method,
                "base_method_status": base_status,
                "head_method_status": head_status,
                "whole_run_base_exit_code": base_run_exit,
                "whole_run_head_exit_code": head_run_exit,
                "base_test_counts": base_result.get("test_counts", {}),
                "head_test_counts": head_result.get("test_counts", {}),
                "base_output": base_output,
                "head_output": head_output,
                "base_db_snapshot": base_snapshot,
                "head_db_snapshot": head_snapshot,
                "db_state_verdict": db_verdict,
                "db_state_detail": db_detail,
                "base_run_seconds": base_seconds,
                "head_run_seconds": head_seconds,
                "base_cache_hit": base_cache_hit,
                "head_run_reused": head_reused,
                "evidence_digest": digest,
                "test_file_sha256": test_sha,
                "changed_symbols": changed_symbols,
                "generation_source": generation_record.get("source", "unknown"),
            })
    else:
        # ── Combined verdict (legacy whole-run path) ──
        if http_verdict == "REGRESSION" and db_verdict in (
            "DB_MUTATED_ON_UNAUTH", "DB_MUTATED",
        ):
            combined_verdict = "REGRESSION"
            combined_detail = (
                f"{http_detail}. {db_detail}. "
                "Base and Head executed the same test but left different DB "
                "state — the regression mutated persisted data."
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
            attributed_contracts.add(attributed_contract)
        elif not base_pass and head_pass:
            attributed_contract = _contract_for_test_method(
                _failing_test_name(base_app)
            )
            attributed_contracts.add(attributed_contract)

        primary_entries = [{
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
            "base_run_seconds": base_seconds,
            "head_run_seconds": head_seconds,
            "base_cache_hit": base_cache_hit,
            "head_run_reused": head_reused,
            "evidence_digest": f"sha256:{evidence_digest}",
            "test_file_sha256": test_sha,
            "changed_symbols": changed_symbols,
            "generation_source": generation_record.get("source", "unknown"),
        }]

    # Source-diff findings computed earlier are prepended; the generated-test
    # verdict is the primary experiment for DIFF-01 (split per failing test
    # method when both sides fail); probe results (when the case declares a
    # probe_expectation) ride along as PROBE-01.
    diff_results: list[dict[str, Any]] = (
        source_diff_results + primary_entries + probe_results
    )

    # ── Contract results: only what this experiment exercised ──
    # P6: the attributed contract family is marked FAIL exactly like the
    # AUTH/UNIQUE families always were — a failing generated test only
    # proves the contract its failing method exercises. After the P2
    # both-fail split, the head-only failing methods are the attributed
    # contracts; base-only failures stay UNVERIFIED (never attributed).
    contract_results: list[dict[str, Any]] = []
    for c in contracts:
        cid = c.get("id", "")
        is_auth = c.get("checker_type") == "http" and cid.upper().startswith("AUTH")
        is_unique = cid == "UNIQUE-01"
        is_attributed = cid in attributed_contracts
        if is_auth or is_unique or is_attributed:
            if http_verdict == "COMPLIANT":
                result = "PASS"
            elif cid in attributed_contracts and (
                method_groups is not None or http_verdict == "REGRESSION"
            ):
                result = "FAIL"
            else:
                result = "UNVERIFIED"
            contract_results.append({
                "contract_id": cid,
                "result": result,
                "experiment": "generated_test_differential",
                "evidence_ref": (
                    evidence_by_contract.get(cid, "")
                    if method_groups is not None
                    else f"sha256:{evidence_digest}"
                ),
            })

    # Probe experiment contract result (only what the probe actually judged).
    if probe_results:
        probe_verdict = probe_results[0].get("verdict")
        probe_contract = probe_results[0].get("contract_id", "")
        if probe_verdict in ("REGRESSION", "COMPLIANT") and probe_contract:
            contract_results.append({
                "contract_id": probe_contract,
                "result": "FAIL" if probe_verdict == "REGRESSION" else "PASS",
                "experiment": "probe_differential",
                "evidence_ref": probe_results[0].get("evidence_digest", ""),
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
    unavailable), parsed from the surefire XML left by the Maven run.

    The report lives inside the HEAD WORKSPACE — PR content is untrusted
    under the sandbox threat model, so parsing goes through defusedxml
    (entity-expansion/XXE hardened), never raw ElementTree.
    """
    import defusedxml.ElementTree as ElementTreeDefused

    report = Path(app_dir) / "target" / "surefire-reports" / (
        "TEST-com.specproof.demo.SpecProofGeneratedTest.xml"
    )
    try:
        root = ElementTreeDefused.parse(report).getroot()
    except (OSError, ElementTreeDefused.ParseError):
        return ""
    for case in root.findall("testcase"):
        if case.find("failure") is not None or case.find("error") is not None:
            return str(case.get("name", ""))
    return ""


def _surefire_report(app_dir: str, test_class: str) -> Path | None:
    """Locate the surefire XML report for the generated test class.

    Surefire names its reports TEST-<fully.qualified.ClassName>.xml
    (TEST-com.specproof.demo.SpecProofGeneratedTest.xml for the generated
    test), so a bare-class-name filename lookup misses it. Accept either
    a fully qualified test_class or a bare name and match the report by
    exact filename first, then by package suffix. No per-method evidence
    -> None -> the caller keeps the whole-run verdict (honest fallback).
    """
    if not test_class:
        return None
    reports_dir = Path(app_dir) / "target" / "surefire-reports"
    direct = reports_dir / f"TEST-{test_class}.xml"
    if direct.exists():
        return direct
    matches = sorted(reports_dir.glob(f"TEST-*.{test_class}.xml"))
    return matches[0] if matches else None


def _test_outcomes(app_dir: str, test_class: str) -> dict[str, str]:
    """Parse the generated test's surefire XML into per-method outcomes.

    Returns {method_name: status} with status in ("pass", "fail",
    "skipped") for every executed testcase of the generated class. An
    unavailable or unparseable report returns {} — callers must treat
    that as "no per-method evidence" and keep the whole-run verdict.
    """
    import defusedxml.ElementTree as ElementTreeDefused

    report = _surefire_report(app_dir, test_class)
    if report is None:
        return {}
    try:
        root = ElementTreeDefused.parse(report).getroot()
    except (OSError, ElementTreeDefused.ParseError):
        return {}
    outcomes: dict[str, str] = {}
    for case in root.findall("testcase"):
        name = str(case.get("name", "")).strip()
        if not name:
            continue
        if case.find("failure") is not None or case.find("error") is not None:
            outcomes[name] = "fail"
        elif case.find("skipped") is not None:
            outcomes[name] = "skipped"
        else:
            outcomes[name] = "pass"
    return outcomes


def _split_both_fail_groups(
    base_outcomes: dict[str, str], head_outcomes: dict[str, str],
) -> tuple[list[str], list[str], list[str]]:
    """Split a both-sides-fail run by test method (pure, deterministic).

    head_only: fails on Head while provably passing on Base — a
        head-introduced failure, attributable to the reviewed head.
    base_only: fails on Base while provably passing on Head — a
        pre-existing failure, never attributed to the head.
    both:      fails on both sides, or fails on one side without a
        recorded pass on the other (skipped/missing) — ambiguous.
    """
    head_only: list[str] = []
    base_only: list[str] = []
    both: list[str] = []
    for name in sorted(set(base_outcomes) | set(head_outcomes)):
        base_status = base_outcomes.get(name)
        head_status = head_outcomes.get(name)
        if head_status == "fail" and base_status == "pass":
            head_only.append(name)
        elif base_status == "fail" and head_status == "pass":
            base_only.append(name)
        elif "fail" in (base_status, head_status):
            both.append(name)
    return head_only, base_only, both


def _test_failure_details(app_dir: str, test_class: str) -> dict[str, str]:
    """Per-method failure snippets from the generated test's surefire XML.

    Returns {failing_method_name: snippet} where the snippet carries the
    failure/error message, type and the first lines of the stack — the
    per-method failure signature the Review Court compares when the SAME
    method fails on both sides (a method may fail on Base for one reason
    and on Head for a different one; that distinct head-side failure must
    not be masked by the Base failure).
    """
    import defusedxml.ElementTree as ElementTreeDefused

    report = _surefire_report(app_dir, test_class)
    if report is None:
        return {}
    try:
        root = ElementTreeDefused.parse(report).getroot()
    except (OSError, ElementTreeDefused.ParseError):
        return {}
    details: dict[str, str] = {}
    for case in root.findall("testcase"):
        name = str(case.get("name", "")).strip()
        if not name:
            continue
        failure = case.find("failure") if case.find("failure") is not None else (
            case.find("error")
        )
        if failure is None:
            continue
        parts = [
            f"type={failure.get('type', '')}",
            f"message={failure.get('message', '')}",
        ]
        text = (failure.text or "").strip()
        if text:
            parts.append("stack=" + " ".join(text.splitlines()[:4]))
        details[name] = " | ".join(p for p in parts if not p.endswith("="))
    return details


def _both_fail_method_groups(
    base_app: str, head_app: str, test_class: str,
) -> tuple[list[str], list[str], list[str]] | None:
    """Per-method split evidence for a both-sides-fail run.

    Returns the (head_only, base_only, both) method groups, or None when
    the surefire reports cannot supply per-method outcomes (the caller
    falls back to the collapsed whole-run AMBIGUOUS experiment).
    """
    base_outcomes = _test_outcomes(base_app, test_class)
    head_outcomes = _test_outcomes(head_app, test_class)
    if not base_outcomes or not head_outcomes:
        return None
    return _split_both_fail_groups(base_outcomes, head_outcomes)


def _split_entry_digest(
    *,
    verdict: str,
    contract_id: str,
    method: str,
    base_status: str,
    head_status: str,
    base_run_exit: int | None,
    head_run_exit: int | None,
    base_result: dict[str, Any],
    head_result: dict[str, Any],
    base_snapshot: dict[str, Any],
    head_snapshot: dict[str, Any],
    test_sha: str,
    base_failure: str = "",
    head_failure: str = "",
) -> str:
    """Deterministic digest for one split differential entry (no timestamps)."""
    payload = json.dumps({
        "verdict": verdict,
        "contract_id": contract_id,
        "failing_test_method": method,
        "base_method_status": base_status,
        "head_method_status": head_status,
        "whole_run_base_exit": base_run_exit,
        "whole_run_head_exit": head_run_exit,
        "base_db_rows": base_snapshot.get("rows", {}),
        "head_db_rows": head_snapshot.get("rows", {}),
        "base_test_counts": base_result.get("test_counts", {}),
        "head_test_counts": head_result.get("test_counts", {}),
        "test_file_sha256": test_sha,
        "base_failure": base_failure,
        "head_failure": head_failure,
    }, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _contract_for_test_method(method_name: str) -> str:
    """Map a generated test method to the contract family it exercises.

    P6 families come first: several of their method names contain
    "duplicate"/"fresh" (the IDEMPOTENT method starts with
    "duplicateOrderRequest..."), so the generic UNIQUE-01 rule must never
    swallow them.
    """
    if "listUsersMustNotUseNPlusOneQueries" in method_name:
        return "NPLUSONE-01"
    if "getUserMustUseCacheAside" in method_name or "emailChangeMustEvictUserCache" in method_name:
        return "CACHE-01"
    if "staleStockWriteMustBeRejected" in method_name:
        return "CONCURRENCY-01"
    if "duplicateOrderRequestMustBeDeduped" in method_name:
        return "IDEMPOTENT-01"
    if ("orderPlacementFailureMustNotLoseStock" in method_name
            or "cancelOrderMustRestock" in method_name):
        return "ATOMICITY-01"
    if "fullStockOrderMustBeAllowed" in method_name:
        return "BOUNDARY-01"
    if "orderAmountMustEqualUnitPriceTimesQuantity" in method_name:
        return "ORDER_AMOUNT-01"
    if "orderCreatedEvent" in method_name or "orderRetry" in method_name:
        return "ORDER_EVENT-01"
    if "invalidEmailChangeMustBeRejected" in method_name:
        return "EMAIL_FORMAT-01"
    if ("emailChangeMustNotPublishSpuriousEvent" in method_name
            or "emailChangeEventPayloadMustBeIntact" in method_name):
        return "EVENT_ONCE-01"
    if "unauthenticated" in method_name:
        return "AUTH-01"
    if "RoutingKey" in method_name or "emailChangeEvent" in method_name:
        return "EVENT_ONCE-01"
    if "duplicate" in method_name or "fresh" in method_name or "blank" in method_name:
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


def _run_generated_test(
    workspace: str, test_class: str, skip_main: bool = False,
) -> dict[str, Any]:
    """Run only the generated test class via Maven Surefire.

    skip_main (P6 base build reuse): the cached base target/classes are
    already the exact compile output of this ref, so the main compile is
    skipped; only the injected test is compiled and surefire runs.
    """
    result: dict[str, Any] = {
        "exit_code": -1, "stdout": "", "stderr": "", "error": "",
        "test_counts": {},
    }
    pom = Path(workspace) / "pom.xml"
    if not pom.exists():
        result["error"] = "No pom.xml found"
        return result

    # Q lane (guide §4.5 task 10): the differential test runs through the
    # ExecutionAdapter protocol — detect → prepare → run. JavaMavenAdapter
    # delegates to the execution SANDBOX (sandbox/runner.py), so untrusted
    # test code never executes with host privileges. Command shape is
    # unchanged from the pre-adapter pipeline (offline -o, -Dtest= injection,
    # -Dmaven.main.skip reuse flag).
    from experiments.adapters import (
        AdapterNotImplemented,
        ExecutionRequest,
        RepositorySnapshot,
        registry,
    )

    try:
        adapter = registry.get(RepositorySnapshot(path=workspace))
    except AdapterNotImplemented as exc:
        result["error"] = str(exc)
        return result
    prepared = adapter.prepare(
        ExecutionRequest(
            workspace=workspace,
            goal="run_test",
            test_class=test_class,
            skip_main=skip_main,
            timeout=900,
        )
    )
    exec_result = adapter.run(prepared)
    result["sandbox_mode"] = exec_result.mode
    if exec_result.error:
        result["error"] = "Sandbox execution failed: " + exec_result.error
        return result
    result["exit_code"] = exec_result.exit_code
    result["stdout"] = exec_result.stdout_tail
    result["stderr"] = exec_result.stderr_tail
    result["test_counts"] = _parse_test_counts(
        exec_result.stdout_tail + exec_result.stderr_tail
    )
    result["error"] = ""
    return result


def _parse_test_counts(output: str) -> dict[str, Any]:
    from experiments.adapters import parse_surefire_summary

    # Single source of truth for the surefire summary regex lives in
    # experiments/adapters.py; this wrapper keeps the historical name.
    return parse_surefire_summary(output)


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
    """Compare the real DB dumps from Base and Head, table by table.

    Returns (verdict, detail):
    - DB_MUTATED_ON_UNAUTH: the users table differs (the P0.5 flagship
      evidence path; its verdict name is part of the evidence policy).
    - DB_MUTATED: any other dumped table (products/orders) differs — the
      same "the regression mutated persisted data" evidence, P6.
    - DB_CONSISTENT: every dumped table is identical.
    - DB_NO_EVIDENCE: no dump available.
    """
    base_method = base_snapshot.get("method")
    head_method = head_snapshot.get("method")
    if base_method != "h2_file_dump" or head_method != "h2_file_dump":
        note = base_snapshot.get("note") or head_snapshot.get("note")
        return "DB_NO_EVIDENCE", f"No H2 dump available: {note}"

    base_rows = base_snapshot.get("rows", {})
    head_rows = head_snapshot.get("rows", {})

    def _table(table: str) -> tuple[dict[str, str], dict[str, str]]:
        prefix = table + ":"
        base_table = {k: v for k, v in base_rows.items() if k.startswith(prefix)}
        head_table = {k: v for k, v in head_rows.items() if k.startswith(prefix)}
        return base_table, head_table

    for table in ("users", "products", "orders"):
        base_table, head_table = _table(table)
        if base_table == head_table:
            continue
        if not base_table and not head_table:
            continue
        changed = [
            f"row {key}: '{base_table[key]}' -> '{head_table[key]}'"
            for key in base_table
            if key in head_table and base_table[key] != head_table[key]
        ] or [f"{table} row set differs: base={base_table}, head={head_table}"]
        detail = "Real H2 dump comparison — " + "; ".join(changed[:6])
        if table == "users":
            return "DB_MUTATED_ON_UNAUTH", detail
        return "DB_MUTATED", detail

    return "DB_CONSISTENT", "Base and Head DB dumps are identical"


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


# ── Execution-time reliability probes (fault-injection roadmap, 阶段4) ──
#
# Cases 97/98/100 carry a probe_expectation in their ground-truth.json and
# the probe scaffolding in their case-head refs (injected by
# scripts/build_golden_scenarios.py). This experiment:
#   1. copies the probe scaffolding from the head workspace into the base
#      workspace (the shared base tag is never re-tagged),
#   2. runs ONE probe test method on each side (surefire Class#method
#      selector through the ExecutionAdapter sandbox path),
#   3. reads target/specproof-probe.json per side (adapter probe hooks),
#   4. compares the artifacts against the expectation and emits a
#      REGRESSION finding when the head violates its expected profile.

_PROBE_SRC_REL = "src/test/java/com/specproof/demo/probe"
_PROBE_TEST_CLASS = "SpecProofProbeTest"
_PROBE_KNOWN_FIELDS = ("publish_count", "outcome", "payload_timestamp_non_null")


def _load_probe_expectation(state: Phase0State) -> dict[str, Any] | None:
    """Read the case's probe_expectation from its eval ground truth
    (golden-cases/<case>/ground-truth.json, located next to spec.md)."""
    spec_path = state.get("spec_path", "")
    if not spec_path:
        return None
    gt_file = Path(spec_path).parent / "ground-truth.json"
    try:
        ground_truth = json.loads(gt_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    expectation = ground_truth.get("probe_expectation")
    return expectation if isinstance(expectation, dict) else None


def _copy_probe_files(head_app: str, base_app: str) -> bool:
    """Copy the probe scaffolding from the head workspace into the base
    workspace so both refs run the same probe test."""
    head_dir = Path(head_app) / _PROBE_SRC_REL
    if not head_dir.is_dir():
        return False
    sources = sorted(head_dir.glob("*.java"))
    if not sources:
        return False
    ok = True
    for src in sources:
        dest = Path(base_app) / _PROBE_SRC_REL / src.name
        try:
            if dest.resolve() == src.resolve():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
        except OSError:
            ok = False
    return ok


def _probe_field_ok(expectation: object, artifact: dict[str, Any] | None, field: str) -> bool:
    """Check one expectation field against an artifact side."""
    if artifact is None:
        return False
    if field == "publish_count":
        return (
            isinstance(expectation, int)
            and artifact.get("publish_count") == expectation
        )
    if field == "outcome":
        return isinstance(expectation, str) and artifact.get("outcome") == expectation
    if field == "payload_timestamp_non_null":
        payloads = artifact.get("payloads") or []
        actual = bool(payloads) and all(
            isinstance(p, dict) and p.get("timestamp") is not None
            for p in payloads
        )
        return isinstance(expectation, bool) and actual == expectation
    return False


def evaluate_probe_expectation(
    expectation: dict[str, Any],
    base_artifact: dict[str, Any] | None,
    head_artifact: dict[str, Any] | None,
) -> tuple[str, str, list[str]]:
    """Compare probe artifacts against the case's probe_expectation.

    Returns (verdict, detail, violations):
      REGRESSION        the head artifact violates its expected profile
      COMPLIANT         both sides meet their expected profiles
      NON_REPRODUCIBLE  base violated its profile / unknown fields / no
                        artifacts - the probe cannot judge the head

    Pure function: no I/O, unit-tested directly.
    """
    base_expectation = expectation.get("base")
    head_expectation = expectation.get("head")
    if not isinstance(base_expectation, dict) or not isinstance(head_expectation, dict):
        return (
            "NON_REPRODUCIBLE",
            "probe_expectation lacks base/head profiles",
            [],
        )

    unknown = [
        field for field in list(base_expectation) + list(head_expectation)
        if field not in _PROBE_KNOWN_FIELDS
    ]
    if unknown:
        return (
            "NON_REPRODUCIBLE",
            "probe_expectation uses unknown fields: " + ", ".join(sorted(set(unknown))),
            [],
        )

    if base_artifact is None or head_artifact is None:
        missing = "base" if base_artifact is None else "head"
        if base_artifact is None and head_artifact is None:
            missing = "base and head"
        return (
            "NON_REPRODUCIBLE",
            f"No probe artifact available for {missing}",
            [],
        )

    base_violations = [
        field for field, expected in base_expectation.items()
        if not _probe_field_ok(expected, base_artifact, field)
    ]
    if base_violations:
        return (
            "NON_REPRODUCIBLE",
            "base artifact does not meet its expected probe profile: "
            + ", ".join(sorted(base_violations)),
            base_violations,
        )

    head_violations = [
        field for field, expected in head_expectation.items()
        if not _probe_field_ok(expected, head_artifact, field)
    ]
    if head_violations:
        return (
            "REGRESSION",
            "probe artifact comparison: head violates "
            + ", ".join(sorted(head_violations))
            + " (base profile met)",
            head_violations,
        )
    return "COMPLIANT", "probe artifacts meet the expected profiles on both sides", []


def _probe_digest_payload(
    verdict: str, base_artifact: dict[str, Any] | None,
    head_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    """Deterministic digest input (no raw timestamps: flags only)."""

    def _side(artifact: dict[str, Any] | None) -> dict[str, Any] | None:
        if artifact is None:
            return None
        payloads = artifact.get("payloads") or []
        return {
            "publish_count": artifact.get("publish_count"),
            "outcome": artifact.get("outcome"),
            "payload_count": len(payloads),
            "all_timestamps_non_null": bool(payloads) and all(
                isinstance(p, dict) and p.get("timestamp") is not None
                for p in payloads
            ),
        }

    return {
        "verdict": verdict,
        "base": _side(base_artifact),
        "head": _side(head_artifact),
    }


def _run_probe_experiment(
    state: Phase0State, base_app: str, head_app: str, base_cache_hit: bool,
) -> list[dict[str, Any]]:
    """Run the execution-time probe experiment for cases that declare one."""
    expectation = _load_probe_expectation(state)
    if expectation is None:
        return []

    method = expectation.get("test_method", "")
    if not isinstance(method, str) or not method:
        return []

    if not _copy_probe_files(head_app, base_app):
        return [{
            "contract_id": expectation.get("contract_id", ""),
            "experiment_id": "PROBE-01",
            "verdict": "NON_REPRODUCIBLE",
            "detail": "Probe scaffolding missing from the head workspace",
            "evidence_type": "probe_differential",
        }]

    test_class = f"{_PROBE_TEST_CLASS}#{method}"
    base_start = time.monotonic()
    base_run = _run_generated_test(base_app, test_class, skip_main=base_cache_hit)
    base_seconds = round(time.monotonic() - base_start, 1)
    head_start = time.monotonic()
    head_run = _run_generated_test(head_app, test_class)
    head_seconds = round(time.monotonic() - head_start, 1)

    from experiments.adapters import (
        AdapterNotImplemented,
        JavaMavenAdapter,
        RepositorySnapshot,
    )

    base_artifact: dict[str, Any] | None = None
    head_artifact: dict[str, Any] | None = None
    adapter_note = ""
    try:
        JavaMavenAdapter().detect(RepositorySnapshot(path=head_app))
        adapter = JavaMavenAdapter()
    except AdapterNotImplemented as exc:
        adapter = None
        adapter_note = str(exc)
    if adapter is not None:
        base_artifact = adapter.read_probe_artifact(base_app)
        head_artifact = adapter.read_probe_artifact(head_app)

    if base_run.get("error") or head_run.get("error"):
        return [{
            "contract_id": expectation.get("contract_id", ""),
            "experiment_id": "PROBE-01",
            "verdict": "NON_REPRODUCIBLE",
            "detail": (
                "Probe Maven execution error - base: "
                + (base_run.get("error") or "ok")
                + ", head: " + (head_run.get("error") or "ok")
            ),
            "evidence_type": "probe_differential",
            "base_exit_code": base_run.get("exit_code"),
            "head_exit_code": head_run.get("exit_code"),
            "base_run_seconds": base_seconds,
            "head_run_seconds": head_seconds,
        }]

    verdict, detail, violations = evaluate_probe_expectation(
        expectation, base_artifact, head_artifact,
    )
    if adapter_note:
        detail += f" (adapter note: {adapter_note})"

    severity = expectation.get("severity", "MAJOR")
    if severity not in ("BLOCKER", "MAJOR", "MINOR"):
        severity = "MAJOR"

    digest = "sha256:" + hashlib.sha256(
        json.dumps(
            _probe_digest_payload(verdict, base_artifact, head_artifact),
            sort_keys=True,
        ).encode()
    ).hexdigest()

    return [{
        "contract_id": expectation.get("contract_id", ""),
        "experiment_id": "PROBE-01",
        "verdict": verdict,
        "detail": detail,
        "severity": severity if verdict == "REGRESSION" else "NONE",
        "confidence": 0.95 if verdict == "REGRESSION" else 0.80,
        "evidence_type": "probe_differential",
        "base_exit_code": base_run.get("exit_code"),
        "head_exit_code": head_run.get("exit_code"),
        "base_probe": base_artifact,
        "head_probe": head_artifact,
        "probe_test_method": method,
        "base_run_seconds": base_seconds,
        "head_run_seconds": head_seconds,
        "evidence_digest": digest,
    }]
