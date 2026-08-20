"""Attribution-accuracy measurement for go-nogo gate #3 (W164 lane).

Builds the synthetic attribution case set under golden-cases-attribution/
and measures PR attribution accuracy through the REAL deterministic
pipeline (same graph invocation as cli.specproof.main eval, LLM off).

Case-set construct (existing demo tags only, no git-state mutation):

* Recall side  -- head_defects: a contract broken ONLY by the reviewed
  head. A correct pipeline attributes the finding to HEAD (confirmed
  finding whose contract matches the head-introduced defect).
* Precision side -- base_defects: a contract already broken on the base
  side of the review. A correct pipeline does NOT attribute it to HEAD.

Two base-side constructs are measured, because the existing demo tags do
not carry a head that preserves a base bug:

* P1 (base fails, head fixed it): base_ref=case-17-head (inverted unique
  guard) vs head_ref=case-18-head -- the pipeline must report the
  pre-existing base failure WITHOUT attributing it to the head.
* P2 (base AND head each have a failure): same ref pair with a
  two-contract spec -- the base side fails UNIQUE-01, the head side fails
  EVENT_ONCE-01. Measures how attribution behaves when both sides fail.

Metrics (defect-level attribution decisions):

    attribution_accuracy_pct = 100
        * (correctly_attributed + correctly_not_attributed)
        / (head_defects + base_defects)

where correctly_not_attributed = base_defects - misattributed_to_head.
missed_attribution counts head defects whose finding is absent or was
downgraded to not_attributed.

Usage:

    python scripts/attribution_cases.py build   # write golden-cases-attribution/
    python scripts/attribution_cases.py run     # measure -> docs/eval/attribution-results.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "golden-cases-attribution"
RESULTS_PATH = REPO_ROOT / "docs" / "eval" / "attribution-results.json"
DEMO_APP_DIR = "demo/spring-backend"

_SPEC_AUTH = (
    "# Attribution Case R1: Authorization Guard Removed (head-introduced)\n\n"
    "The change-email endpoint must require authentication: unauthenticated "
    "requests must receive 401 Unauthorized and must not modify the stored "
    "email.\n"
)
_SPEC_UNIQUE = (
    "# Attribution Case: Duplicate Email Rejection (UNIQUE-01)\n\n"
    "The change-email endpoint must reject duplicate emails: changing to an "
    "email that is already in use must fail, while changing to a fresh email "
    "must succeed.\n"
)
_SPEC_EVENT = (
    "# Attribution Case: Email Event Routing Key (EVENT_ONCE-01)\n\n"
    "The change-email endpoint must publish the email.changed event exactly "
    "once to the documented routing key.\n"
)
_SPEC_CACHE = (
    "# Attribution Case: Cache Eviction On Email Change (CACHE-01)\n\n"
    "After an email change, the cached user entry must be evicted so "
    "subsequent reads see the new email.\n"
)
_SPEC_CONCURRENCY = (
    "# Attribution Case: Optimistic Locking (CONCURRENCY-01)\n\n"
    "Product stock updates must use optimistic concurrency control "
    "(@Version): a stale write must be rejected, never silently overwritten."
    "\n"
)
_SPEC_TRANSACTION = (
    "# Attribution Case: Transaction Boundary (TRANSACTION-01)\n\n"
    "Cancelling an order must run inside a transaction so the status change "
    "and the stock restore stay atomic.\n"
)

CASES: list[dict[str, Any]] = [
    {
        "id": "case-att-01-head-auth",
        "base_ref": "base",
        "head_ref": "head-v1",
        "spec": _SPEC_AUTH,
        "expected_severity": "BLOCKER",
        "expected_contract": "AUTH-01",
        "expected_evidence_type": "base_pass_head_fail",
        "should_detect": True,
        "head_defects": [{
            "contract_id": "AUTH-01",
            "kind": "regression",
            "description": "@PreAuthorize guard removed by head-v1",
        }],
        "base_defects": [],
    },
    {
        "id": "case-att-02-head-unique-inversion",
        "base_ref": "base",
        "head_ref": "case-17-head",
        "spec": _SPEC_UNIQUE,
        "expected_severity": "BLOCKER",
        "expected_contract": "UNIQUE-01",
        "expected_evidence_type": "base_pass_head_fail",
        "should_detect": True,
        "head_defects": [{
            "contract_id": "UNIQUE-01",
            "kind": "regression",
            "description": "duplicate-email guard inverted by case-17-head",
        }],
        "base_defects": [],
    },
    {
        "id": "case-att-03-head-routing-key",
        "base_ref": "base",
        "head_ref": "case-18-head",
        "spec": _SPEC_EVENT,
        "expected_severity": "MAJOR",
        "expected_contract": "EVENT_ONCE-01",
        "expected_evidence_type": "base_pass_head_fail",
        "should_detect": True,
        "head_defects": [{
            "contract_id": "EVENT_ONCE-01",
            "kind": "regression",
            "description": "email.changed routing key broken by case-18-head",
        }],
        "base_defects": [],
    },
    {
        "id": "case-att-04-head-cache-eviction",
        "base_ref": "base",
        "head_ref": "case-56-head",
        "spec": _SPEC_CACHE,
        "expected_severity": "MAJOR",
        "expected_contract": "CACHE-01",
        "expected_evidence_type": "base_pass_head_fail",
        "should_detect": True,
        "head_defects": [{
            "contract_id": "CACHE-01",
            "kind": "regression",
            "description": "user-cache eviction removed by case-56-head",
        }],
        "base_defects": [],
    },
    {
        "id": "case-att-05-head-optimistic-lock",
        "base_ref": "base",
        "head_ref": "case-29-head",
        "spec": _SPEC_CONCURRENCY,
        "expected_severity": "BLOCKER",
        "expected_contract": "CONCURRENCY-01",
        "expected_evidence_type": "base_pass_head_fail",
        "should_detect": True,
        "head_defects": [{
            "contract_id": "CONCURRENCY-01",
            "kind": "regression",
            "description": "@Version optimistic lock removed by case-29-head",
        }],
        "base_defects": [],
    },
    {
        "id": "case-att-06-head-transaction-boundary",
        "base_ref": "base",
        "head_ref": "case-28-head",
        "spec": _SPEC_TRANSACTION,
        "expected_severity": "MAJOR",
        "expected_contract": "TRANSACTION-01",
        "expected_evidence_type": "java_source_diff",
        "should_detect": True,
        "head_defects": [{
            "contract_id": "TRANSACTION-01",
            "kind": "regression",
            "description": "@Transactional removed by case-28-head (static evidence)",
        }],
        "base_defects": [],
    },
    {
        "id": "case-att-07-base-unique-preexisting",
        "base_ref": "case-17-head",
        "head_ref": "case-18-head",
        "spec": _SPEC_UNIQUE,
        "expected_severity": "NONE",
        "expected_contract": "UNIQUE-01",
        "expected_evidence_type": "none",
        "should_detect": False,
        "head_defects": [],
        "base_defects": [{
            "contract_id": "UNIQUE-01",
            "kind": "pre_existing",
            "description": (
                "inverted unique guard already present on the base side "
                "(case-17-head); the reviewed head (case-18-head) does not "
                "carry it - the failure must not be attributed to the head"
            ),
        }],
    },
    {
        "id": "case-att-08-base-and-head-both-fail",
        "base_ref": "case-17-head",
        "head_ref": "case-18-head",
        "spec": _SPEC_UNIQUE + "\n" + _SPEC_EVENT,
        "expected_severity": "MAJOR",
        "expected_contract": "EVENT_ONCE-01",
        "expected_evidence_type": "base_pass_head_fail",
        "should_detect": True,
        "head_defects": [{
            "contract_id": "EVENT_ONCE-01",
            "kind": "regression",
            "description": "routing key broken by the reviewed head (case-18-head)",
        }],
        "base_defects": [{
            "contract_id": "UNIQUE-01",
            "kind": "pre_existing",
            "description": (
                "inverted unique guard already present on the base side "
                "(case-17-head): Base AND Head each carry their own failure"
            ),
        }],
    },
]



def _ground_truth(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected_severity": case["expected_severity"],
        "expected_contract": case["expected_contract"],
        "expected_evidence_type": case["expected_evidence_type"],
        "should_detect": case["should_detect"],
        "attribution": {
            "head_defects": case["head_defects"],
            "base_defects": case["base_defects"],
        },
    }


def _scenario(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "2.0",
        "base_ref": case["base_ref"],
        "head_ref": case["head_ref"],
        "note": (
            "Attribution case set (W164, go-nogo gate #3): existing demo "
            "tags only, built by scripts/attribution_cases.py"
        ),
    }


def build_cases() -> list[Path]:
    """Write golden-cases-attribution/<case>/{spec.md,ground-truth.json,scenario.json}."""
    written: list[Path] = []
    CASES_DIR.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        case_dir = CASES_DIR / case["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "spec.md").write_text(case["spec"], encoding="utf-8")
        (case_dir / "ground-truth.json").write_text(
            json.dumps(_ground_truth(case), indent=2) + "\n", encoding="utf-8",
        )
        (case_dir / "scenario.json").write_text(
            json.dumps(_scenario(case), indent=2) + "\n", encoding="utf-8",
        )
        written.append(case_dir)
    return written


def _attributed_contracts(findings: list[dict[str, Any]]) -> set[str]:
    """Confirmed findings are exactly the findings the court kept attributed to HEAD."""
    return {
        str(f.get("contract_id") or "")
        for f in findings
        if f.get("status") in ("confirmed", "needs_confirmation")
    }


def _not_attributed_contracts(candidates: list[dict[str, Any]]) -> set[str]:
    """Contracts the court downgraded as pre-existing (Base also fails)."""
    return {
        str(c.get("contract_id") or "")
        for c in candidates
        if c.get("policy_outcome") == "not_attributed"
    }


def _diff_summary(diff_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dr in diff_results:
        if "base_exit_code" not in dr and "head_exit_code" not in dr:
            continue
        rows.append({
            "contract_id": dr.get("contract_id", ""),
            "verdict": dr.get("verdict", ""),
            "base_exit_code": dr.get("base_exit_code"),
            "head_exit_code": dr.get("head_exit_code"),
        })
    return rows


def _analyze_case(
    case: dict[str, Any], final: dict[str, Any], duration_ms: int,
) -> dict[str, Any]:
    confirmed = final.get("confirmed_findings", [])
    candidates = final.get("candidate_findings", [])
    attributed = _attributed_contracts(confirmed)
    not_attributed = _not_attributed_contracts(candidates)

    head_defects = [d["contract_id"] for d in case["head_defects"]]
    base_defects = [d["contract_id"] for d in case["base_defects"]]

    correctly_attributed = 0
    missed = 0
    missed_detail: list[str] = []
    for contract_id in head_defects:
        if contract_id in attributed:
            correctly_attributed += 1
        else:
            missed += 1
            if contract_id in not_attributed:
                missed_detail.append(
                    contract_id + ": finding downgraded to not_attributed"
                )
            else:
                missed_detail.append(contract_id + ": no finding produced")

    misattributed = 0
    misattributed_contracts: list[str] = []
    for contract_id in base_defects:
        if contract_id in attributed:
            misattributed += 1
            misattributed_contracts.append(contract_id)

    return {
        "case": case["id"],
        "scenario": {
            "base_ref": case["base_ref"],
            "head_ref": case["head_ref"],
        },
        "head_defects": head_defects,
        "base_defects": base_defects,
        "correctly_attributed": correctly_attributed,
        "missed_attribution": missed,
        "missed_detail": missed_detail,
        "misattributed_to_head": misattributed,
        "misattributed_contracts": misattributed_contracts,
        "correctly_not_attributed": len(base_defects) - misattributed,
        "confirmed_contracts": sorted(attributed),
        "not_attributed_contracts": sorted(not_attributed),
        "diff_results": _diff_summary(final.get("diff_results", [])),
        "duration_ms": duration_ms,
        "pipeline_error": final.get("pipeline_error", ""),
    }


def run_measurement() -> dict[str, Any]:
    """Run every case through the real pipeline and compute attribution metrics."""
    import sys

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from agent.graph import build_phase0_graph  # noqa: PLC0415
    from agent.state import initial_state  # noqa: PLC0415
    from cli.specproof.commands.eval import _cleanup_worktrees  # noqa: PLC0415

    graph = build_phase0_graph()
    repo_resolved = str(REPO_ROOT.resolve())
    rows: list[dict[str, Any]] = []

    for case in CASES:
        case_dir = CASES_DIR / case["id"]
        spec_file = case_dir / "spec.md"
        if not spec_file.exists():
            build_cases()
        state = initial_state(
            repo_path=repo_resolved,
            base_ref=case["base_ref"],
            head_ref=case["head_ref"],
            spec_path=str(spec_file),
            depth="FAST",
        )
        state["use_llm"] = False
        state["output_dir"] = str(REPO_ROOT / "reports")
        state["app_dir"] = DEMO_APP_DIR

        started_at = time.perf_counter()
        final: dict[str, Any] = {}
        try:
            final = graph.invoke(state)
        except Exception as exc:  # noqa: BLE001
            final = {"pipeline_error": type(exc).__name__ + ": " + str(exc)}
        duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
        _cleanup_worktrees(repo_resolved, final)
        rows.append(_analyze_case(case, final, duration_ms))
        print(
            "[" + case["id"] + "] attributed="
            + str(rows[-1]["correctly_attributed"]) + "/"
            + str(len(case["head_defects"]))
            + " missed=" + str(rows[-1]["missed_attribution"])
            + " misattributed=" + str(rows[-1]["misattributed_to_head"])
            + " (" + str(duration_ms) + " ms)"
        )

    head_defects = sum(len(c["head_defects"]) for c in CASES)
    base_defects = sum(len(c["base_defects"]) for c in CASES)
    correctly_attributed = sum(r["correctly_attributed"] for r in rows)
    missed_attribution = sum(r["missed_attribution"] for r in rows)
    misattributed_to_head = sum(r["misattributed_to_head"] for r in rows)
    correctly_not_attributed = base_defects - misattributed_to_head
    total_decisions = head_defects + base_defects
    accuracy = (
        100.0 * (correctly_attributed + correctly_not_attributed) / total_decisions
        if total_decisions else 100.0
    )

    return {
        "generated_by": "scripts/attribution_cases.py run",
        "gate": "go-nogo #3 PR 归因准确率 >= 90%",
        "cases": len(rows),
        "head_defects": head_defects,
        "base_defects": base_defects,
        "correctly_attributed": correctly_attributed,
        "missed_attribution": missed_attribution,
        "misattributed_to_head": misattributed_to_head,
        "correctly_not_attributed": correctly_not_attributed,
        "attribution_accuracy_pct": round(accuracy, 1),
        "formula": (
            "attribution_accuracy_pct = 100 * (correctly_attributed + "
            "correctly_not_attributed) / (head_defects + base_defects)"
        ),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="attribution_cases",
        description="Build and measure the go-nogo #3 attribution case set.",
    )
    parser.add_argument(
        "command",
        choices=("build", "run"),
        help="build writes the case dirs; run measures and writes the results JSON",
    )
    args = parser.parse_args(argv)

    if args.command == "build":
        for path in build_cases():
            print("built " + str(path.relative_to(REPO_ROOT)))
        return 0

    results = run_measurement()
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(
        "attribution_accuracy_pct=" + str(results["attribution_accuracy_pct"])
        + " (correctly_attributed=" + str(results["correctly_attributed"]) + "/"
        + str(results["head_defects"])
        + ", misattributed=" + str(results["misattributed_to_head"]) + "/"
        + str(results["base_defects"])
        + ", missed=" + str(results["missed_attribution"]) + ")"
    )
    print("wrote " + str(RESULTS_PATH.relative_to(REPO_ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

