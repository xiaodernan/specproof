"""#154 — the job path listens to the RELEASE gates, not just the CLI.

#151 made `specproof verify` listen to the release gates before signing;
#152 unified the "nothing was judged" reading. The worker path kept its own
quiet bypass: `_terminal_status_from_state` and `_state_summary` computed
their verdict from contract rows alone (`agent/worker.py`), so a RELEASE job
whose evidence had just failed to reproduce was still persisted as VERIFIED
into MySQL, announced to notify channels and rendered on the dashboard with
a `coverage_reason` that could not name the gate.

These tests pin the job-path call sites onto the same shared policy
(`evaluate_acceptance`), with payloads in the exact shape
`agent/nodes/run_release_checks.py` writes (`gates.reproducibility` mapping
with a `passed` flag; `gates.capsule_integrity` list of digest rows).

Witness plan (arms in .scratch/g154/mutate_154.py, predictions written here
BEFORE the first run; test numbers are the order below):

* A1 `_terminal_status_from_state` drops `release=` ⇒ {1,2,3} red;
  4,5,7 stay green (4 is the absence-leg, 5 the no-rewrite-leg, 7 the
  passage-leg). **6 also stays green, on purpose**: it asserts the two
  readers agree, and A1 keeps them agreeing through the `verdict`
  parameter — wrongly, but jointly. The veto half of that agreement is
  pinned by 1-3, the summary half by A2; the agreement leg itself is only
  meaningful when at least one reader still listens.
* A2 `_state_summary` drops `release=` ⇒ {1,6} red — 2/3/4/5/7 read the
  terminal status, not the summary's coverage_reason.
* A3 `_terminal_status_from_state` calls `evaluate_verification` (full
  bypass) ⇒ same set as A1: {1,2,3}.

The four behaviour shapes mirror #151/#152 so one vocabulary serves three
readers: refusal blocks; unjudged blocks; empty rosters block; absence is
not agreement and rewrites never move a verdict upward.
"""
from typing import Any

from agent.worker import _state_summary, _terminal_status_from_state


def passing_state(release: dict[str, Any] | None = None) -> dict[str, Any]:
    """A state whose contracts all passed — the only verdict a veto can flip."""
    state: dict[str, Any] = {
        "matrix": {
            "rows": [{
                "contract_id": "C-1", "result": "PASS",
                "experiment": "DIFF-01", "evidence": "ev-1",
            }],
            "total_contracts": 1, "passed": 1, "failed": 0, "unverified": 0,
            "total_rows": 1,
        },
        "contracts": [{"id": "C-1"}],
        "confirmed_findings": [],
        "errors": [],
    }
    if release is not None:
        state["release_results"] = release
    return state


def refused_release() -> dict[str, Any]:
    """The shape run_release_checks.py writes when the rerun flips polarity."""
    return {
        "gates": {
            "reproducibility": {
                "passed": False, "first_head_pass": False, "rerun_head_pass": True,
                "rerun_mode": "docker_sandbox", "error": "",
            },
            "capsule_integrity": [{"capsule": "capsule-c1.zip", "digest_ok": True}],
        },
        "passed": False,
    }


def test_refused_release_gate_blocks_the_job_summary_and_names_itself():
    state = passing_state(refused_release())
    assert _terminal_status_from_state(state) == "BLOCKED"
    summary = _state_summary(state, "BLOCKED")
    assert "RELEASE 档发布门 reproducibility" in summary["coverage_reason"]
    # The veto refuses, it does not erase: the passing contract is still a
    # passing contract, and the counts keep saying so.
    assert summary["matrix_passed"] == 1


def test_an_unjudged_gate_row_blocks_the_job_too():
    """The job still ends — as NEEDS_REVIEW, not BLOCKED.

    A gate that could not be judged refuses the acceptance (an unchecked
    gate may never support one), but nothing is proven wrong: the job
    ends in the state that says a human has to look.
    """
    entry = refused_release()
    entry["gates"]["reproducibility"] = {"first_head_pass": False}  # no flag
    entry["passed"] = True  # the node's own summary believed it passed
    assert _terminal_status_from_state(passing_state(entry)) == "NEEDS_REVIEW"


def test_an_empty_gate_roster_blocks_the_job_too():
    # #152's second口径 at the job level: a flag alone cannot support an
    # acceptance, and "校验了空集合" is 未判定, which refuses — as an
    # evidence gap, not as a proven defect.
    entry = {
        "gates": {
            "reproducibility": {"passed": True, "first_head_pass": False,
                                "rerun_head_pass": False},
            "capsule_integrity": [],
        },
        "passed": True,
    }
    assert _terminal_status_from_state(passing_state(entry)) == "NEEDS_REVIEW"


def test_jobs_without_a_release_verdict_keep_their_verdicts():
    # Absent key (FAST/DEEP, or the node never ran), empty payload, and a
    # payload without gates are all "no gate verdict to listen to".
    assert _terminal_status_from_state(passing_state()) == "VERIFIED"
    assert _terminal_status_from_state(passing_state({})) == "VERIFIED"
    assert _terminal_status_from_state(
        passing_state({"release_note": "RELEASE tier not requested"})
    ) == "VERIFIED"


def test_the_veto_never_rewrites_failure_or_block():
    refused = refused_release()
    failed_state = passing_state(refused) | {"errors": ["maven compile failed"]}
    assert _terminal_status_from_state(failed_state) == "FAILED"
    # A BLOCKED decision comes back unchanged: the veto only ever downgrades
    # VERIFIED, and it does not bolt gate prose onto an already-blocked job.
    blocked_state = passing_state(refused) | {
        "confirmed_findings": [{"id": "F-1", "severity": "BLOCKER"}],
    }
    verdict = _terminal_status_from_state(blocked_state)
    assert verdict == "BLOCKED"
    assert "RELEASE 档发布门" not in _state_summary(blocked_state, verdict)["coverage_reason"]


def test_terminal_status_and_summary_tell_the_same_story():
    state = passing_state(refused_release())
    verdict = _terminal_status_from_state(state)
    summary = _state_summary(state, verdict)
    assert summary["verdict"] == verdict
    assert "RELEASE 档发布门" in summary["coverage_reason"]


def test_full_gate_passage_verifies_the_job():
    # The no-over-refusal leg: every row 通过 and the node's own flag agrees
    # ⇒ the strongest tier still ends in VERIFIED.
    passed_release = {
        "gates": {
            "reproducibility": {
                "passed": True, "first_head_pass": False, "rerun_head_pass": False,
                "rerun_mode": "docker_sandbox", "error": "",
            },
            "capsule_integrity": [{"capsule": "capsule-c1.zip", "digest_ok": True}],
        },
        "passed": True,
    }
    assert _terminal_status_from_state(passing_state(passed_release)) == "VERIFIED"
