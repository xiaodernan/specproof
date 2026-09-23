"""Self-test differential verdict (roadmap 4a groundwork — NOT wired to execution).

A "run the repository's own test suite on Base and Head" differential can
produce real ``base_pass_head_fail`` evidence for Node/Python repos WITHOUT an
LLM: if the project's own tests are all green on Base and something fails on
Head, that is a reproducible regression.

But the ``NodeAdapter``/``PythonAdapter`` in ``experiments/adapters.py`` are
local-first — they execute on the HOST with no container sandbox. Wiring that
path naively would run UNTRUSTED PR-authored tests on the host, directly
violating the ``api/routes/jobs.py`` "verification API must never become a
remote execution surface" red line.

So this module ships ONLY the pure, offline-verifiable pieces:

  * ``self_test_execution_allowed()`` — the default-off execution gate policy.
  * ``self_test_verdict()``          — the verdict math over parsed test-count
    summaries (whatever shape the adapter's ``parse_*_summary`` returns).

The execution wiring is INTENTIONALLY ABSENT until an equivalent Docker sandbox
for Node/Python exists (roadmap ④, whose argv-level groundwork already landed in
``sandbox/runner.py``). Nothing here imports an adapter, spawns a process, or
touches a workspace — importing this module has no side effects and cannot run
untrusted code. When the sandbox lands, ``run_differential`` gains a caller of
``self_test_verdict`` guarded by ``self_test_execution_allowed()``.
"""
from __future__ import annotations

import os

#: Env var gating local-first (host, unsandboxed) self-test execution. Default
#: OFF: an unset value means "never execute a repo's own tests on the host".
ALLOW_LOCAL_TEST_EXEC_ENV = "SPECPROOF_ALLOW_LOCAL_TEST_EXEC"

_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Verdict vocabulary kept aligned with run_differential's strings so a future
# wiring can drop these straight into a diff_results entry without a mapping
# layer. REGRESSION = base green / head broken (the money verdict).
VERDICT_REGRESSION = "REGRESSION"
VERDICT_COMPLIANT = "COMPLIANT"
VERDICT_AMBIGUOUS = "AMBIGUOUS"
VERDICT_UNEXPECTED_FIX = "UNEXPECTED_FIX"
# No usable counts on one side (a summary that parsed to zero tests, e.g. a
# build/test command that never ran or a reporter we cannot parse): an honest
# "no evidence" that must NOT be laundered into a pass.
VERDICT_NO_EVIDENCE = "NON_REPRODUCIBLE"


def self_test_execution_allowed() -> bool:
    """True only when the operator has EXPLICITLY enabled host self-test runs.

    Fail-closed: any unparseable/absent value yields False. Turning this on is
    a deliberate, documented opt-in to run untrusted repo tests on the host
    (no sandbox), and must be paired with honest UI labeling — see roadmap ④/4a.
    """
    return os.getenv(ALLOW_LOCAL_TEST_EXEC_ENV, "").strip().lower() in _TRUTHY


def _failing(counts: dict[str, int] | None) -> int | None:
    """How many tests failed+errored in one side's summary, or None if the
    summary carries no usable signal (missing keys or zero tests — an empty
    run is not evidence of a green suite).

    Handles all three adapter reporters: surefire uses ``failures`` while
    pytest/node use ``failed``; both are summed alongside ``errors``.
    """
    if not counts:
        return None
    tests = counts.get("tests")
    if tests is None:
        parts = [int(counts.get(k, 0) or 0) for k in
                 ("passed", "failed", "failures", "errors", "skipped")]
        if not any(parts):
            return None
        tests = sum(parts)
    if int(tests) <= 0:
        return None
    return (
        int(counts.get("failed", 0) or 0)
        + int(counts.get("failures", 0) or 0)
        + int(counts.get("errors", 0) or 0)
    )


def self_test_verdict(
    base_counts: dict[str, int] | None,
    head_counts: dict[str, int] | None,
) -> tuple[str, str]:
    """Compare base/head self-test summaries into a differential verdict.

    ``base_counts``/``head_counts`` are the dicts returned by the adapters'
    ``parse_surefire_summary`` / ``parse_pytest_summary`` /
    ``parse_node_test_summary`` (keys include ``tests`` and ``failed``;
    ``errors`` where the reporter separates them). Returns ``(verdict, detail)``.

    A zero-test summary on either side is NO_EVIDENCE, never COMPLIANT — we do
    not manufacture a pass from "the command ran and printed nothing".
    """
    base_fail = _failing(base_counts)
    head_fail = _failing(head_counts)
    if base_fail is None or head_fail is None:
        missing = []
        if base_fail is None:
            missing.append("base")
        if head_fail is None:
            missing.append("head")
        return (
            VERDICT_NO_EVIDENCE,
            f"self-test differential has no parseable test summary for "
            f"{' and '.join(missing)} (command ran but produced no counts)",
        )

    base_green = base_fail == 0
    head_green = head_fail == 0

    if base_green and not head_green:
        return (
            VERDICT_REGRESSION,
            f"Repository self-tests pass on Base ({_tests(base_counts)} tests) "
            f"but {head_fail} fail on Head — head-introduced regression",
        )
    if base_green and head_green:
        return (
            VERDICT_COMPLIANT,
            f"Repository self-tests pass on both Base and Head "
            f"({_tests(head_counts)} tests)",
        )
    if not base_green and head_green:
        return (
            VERDICT_UNEXPECTED_FIX,
            f"Repository self-tests fail on Base ({base_fail} failing) but pass "
            "on Head — pre-existing base failure, not attributed to Head",
        )
    return (
        VERDICT_AMBIGUOUS,
        f"Repository self-tests fail on both Base ({base_fail}) and "
        f"Head ({head_fail}) — not attributable to this change",
    )


def _tests(counts: dict[str, int] | None) -> int:
    if not counts:
        return 0
    return int(counts.get("tests", 0) or 0)
