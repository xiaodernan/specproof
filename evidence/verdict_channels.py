"""`verdict` is one field name worn by fifteen different scales.

DRILLS "已知未收口" recorded this as the last open vocabulary line item: the same
word appears as a job's summary outcome, as a report's conclusion, as the agent
lane's result projection, as a matrix row's `result`, as an evaluation case's
judgement, as a Craft loop checkpoint and as a benchmark's classification — so
no answer existed to "which scale does this word belong to". The ledger's "25 个
字面量" was one scan shape's count; re-measured at 63615c5 with six shapes
(dict-key, kwarg, kwarg-collection, assignment/subscription write, attribute and
variable compare) plus `.get("verdict", default)`: **39 distinct literals in
product code**, 18 further writes whose value is an expression the scanner
cannot enumerate, and two files that must not count at all (a third-party
dataset fixture and a demo script that writes prose).

So the channels are declared here: which files may mention the field, what
words they may write, and — where a word has no literal spelling — the exact
line that produces it. `tests/unit/test_verdict_channel_parity.py` re-derives
every one of those facts from source and asserts both directions, so this file
cannot drift into a description of code that no longer exists.

Three mistakes this registry exists to prevent, all observed while measuring:

1. `apps/web/src/ui/util.tsx` glossed eight words for a field the worker only
   ever writes three of — five were status words (STALE, ERROR, CANCELLED) or a
   matrix word (UNVERIFIED) that had migrated into a verdict vocabulary.
2. `evidence/report.py` writes "NEEDS REVIEW" with a space while
   `integrations/notify/templates.py` canonicalises it to `NEEDS_REVIEW`; two
   spellings of one word are two vocabularies unless someone says which is
   canonical.
3. `api/routes/agent_console.py` can write COMPLETED and UNKNOWN into a
   `verdict` that no gloss knew, so a merged job's headline would print raw
   English.

Channels whose authority already exists elsewhere (a `Literal`, a pydantic
`pattern`, the state machine) are referenced through `source` instead of copied.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class VerdictChannel:
    #: Channel id, stable: it appears in the parity test's failure messages.
    key: str
    #: The field (or parameter) this scale actually lands in.
    field: str
    #: Repo-relative files allowed to mention the field. A file whose `verdict`
    #: literals no channel owns fails the parity gate, by name and line.
    owners: tuple[str, ...]
    #: The declared domain. Every entry is either written literally by an owner
    #: or carries a `witnesses` entry pointing at the line that writes it.
    scale: frozenset[str]
    #: value -> "<path>:<line>" of the code that produces it when no literal
    #: spelling exists (conditional expressions, `dict.get` fallbacks). The test
    #: opens the file and requires the token on that line, so a witness cannot
    #: park a word nobody writes.
    witnesses: dict[str, str] | None = None
    #: Import path or "<module>::<name>" of an authoritative declaration whose
    #: value set must equal `scale`. Empty means this file is the authority.
    source: str = ""
    #: Files allowed to write a non-literal (a variable, a conditional): the
    #: value cannot be read statically, so only the ownership rule applies.
    opaque: tuple[str, ...] = ()
    note: str = ""


CHANNELS: Final[dict[str, VerdictChannel]] = {
    # ── the verification lane ────────────────────────────────────────────────
    "job_summary": VerdictChannel(
        key="job_summary",
        field="verification_jobs.summary.verdict (written with the terminal status)",
        owners=(
            "agent/worker.py",
            "integrations/notify/templates.py",
            "ops/drills.py",
            "scripts/seed_demo.py",
        ),
        scale=frozenset({"VERIFIED", "BLOCKED", "FAILED"}),
        opaque=(
            "agent/worker.py",
            "integrations/notify/templates.py",
            "ops/drills.py",
            "scripts/seed_demo.py",
        ),
        note=(
            "The 验证结论 headline. `_terminal_status_from_state` returns "
            "`evaluate_verification(...).status`, so this field and the job's "
            "terminal status are the same three words in the same write "
            "(worker.py:306). `evidence/verdict.py` is where those three words "
            "are chosen; it never names the field `verdict`, which is why the "
            "parity test reads its `VerificationDecision(...)` call directly."
        ),
    ),
    "report_verdict": VerdictChannel(
        key="report_verdict",
        field="report.json / certificate verdict (what `specproof verify` prints)",
        owners=(
            "evidence/report.py",
            "mcp/tools.py",
            "cli/specproof/commands/verify.py",
        ),
        scale=frozenset({"VERIFIED", "BLOCKED", "NEEDS REVIEW"}),
        opaque=(
            "evidence/report.py",
            "mcp/tools.py",
            "cli/specproof/commands/verify.py",
        ),
        note=(
            "`evidence/report.py` downgrades BLOCKED to \"NEEDS REVIEW\" when "
            "nothing actually failed — a report-only word. The space spelling is "
            "canonical here; notify folds it to NEEDS_REVIEW on read."
        ),
    ),
    "result_json": VerdictChannel(
        key="result_json",
        field="result_json.verdict (the agent lane's execution result projection)",
        owners=("api/agent_runtime.py", "api/routes/agent_console.py"),
        scale=frozenset({"FAILED", "CANCELLED", "COMPLETED", "UNKNOWN"}),
        witnesses={"UNKNOWN": "api/routes/agent_console.py:455"},
        opaque=("api/agent_runtime.py", "api/routes/agent_console.py"),
        note=(
            "Console writes: a plan/step/gate rejection is FAILED, a supervisor "
            "cancel is CANCELLED, a gate approval is COMPLETED, and a stored "
            "result that carries no verdict at all is synthesised as UNKNOWN "
            "rather than shown as empty. The console page dumps this JSON raw."
        ),
    ),
    "accept": VerdictChannel(
        key="accept",
        field="accept.json.verdict (independent acceptance projection)",
        owners=("craft/accept.py", "cli/specproof/commands/craft.py"),
        scale=frozenset({"VERIFIED", "BLOCKED", "ERROR"}),
        witnesses={"ERROR": "craft/accept.py:475"},
        source="craft.accept::AcceptVerdict",
        opaque=("craft/accept.py",),
        note=(
            "The runtime lane never issues VERIFIED (the certificate belongs to "
            "`specproof craft accept`), which is why the Web gloss is keyed off "
            "`gates.overall` rather than the token."
        ),
    ),
    # ── matrix and differential evidence ────────────────────────────────────
    "matrix_row": VerdictChannel(
        key="matrix_row",
        field="matrix row `result` (received as a parameter named verdict)",
        owners=("agent/matrix_policy.py",),
        scale=frozenset({"PASS", "FAIL", "UNVERIFIED"}),
        opaque=("agent/matrix_policy.py",),
        note=(
            "Same three words as `evidence/verdict.py`'s row `result`; they are "
            "read here as `verdict`, which is how a row-level gate and a "
            "job-level verdict were once confused. The merge itself is a call "
            "(`_merge_verdict`) whose words the scanner cannot enumerate."
        ),
    ),
    "matrix_diff": VerdictChannel(
        key="matrix_diff",
        field="diff_results[].verdict (and the copies of it)",
        owners=(
            "agent/nodes/build_matrix.py",
            "agent/nodes/run_differential.py",
            "agent/review_court/policy.py",
            "evidence/lineage.py",
            "scripts/attribution_cases.py",
        ),
        scale=frozenset({
            "REGRESSION", "NON_REPRODUCIBLE", "UNEXPECTED_FIX", "AMBIGUOUS",
        }),
        opaque=(
            "agent/nodes/build_matrix.py",
            "agent/nodes/run_differential.py",
            "agent/review_court/policy.py",
            "evidence/lineage.py",
            "scripts/attribution_cases.py",
        ),
        note=(
            "Per-contract differential outcome; feeds the matrix attribution "
            "gate (#91). The four copies are pass-throughs of the same record, "
            "which is why they may only re-state words run_differential wrote."
        ),
    ),
    # ── evaluation ──────────────────────────────────────────────────────────
    "eval_case": VerdictChannel(
        key="eval_case",
        field="evaluation case report verdict",
        owners=(
            "cli/specproof/commands/baseline.py",
            "cli/specproof/commands/eval.py",
        ),
        scale=frozenset({"PASS", "PARTIAL", "MISS", "FALSE_POSITIVE"}),
        opaque=(
            "cli/specproof/commands/baseline.py",
            "cli/specproof/commands/eval.py",
        ),
        note=(
            "「检出结果与预期是否一致」，与需求覆盖的 PASS/FAIL 不是同一套语义："
            "PASS=与预期一致，PARTIAL=检出但少于预期数量，MISS=漏检，"
            "FALSE_POSITIVE=误报。"
        ),
    ),
    # ── craft ───────────────────────────────────────────────────────────────
    "craft_loop": VerdictChannel(
        key="craft_loop",
        field="craft loop checkpoint verdict",
        owners=("craft/loop.py",),
        scale=frozenset({"green", "progress", "stuck", "cancelled", "interrupted"}),
        opaque=("craft/loop.py",),
        note="Per-step checkpoint state, lower case by design.",
    ),
    "craft_bench": VerdictChannel(
        key="craft_bench",
        field="scripts/bench_craft.py TaskVerdict.verdict",
        owners=("scripts/bench_craft.py",),
        scale=frozenset({
            "COMPLETE", "INTERCEPTED", "RECOVERED", "RECOVERY_FAILED",
            "APPROVAL_REFUSED", "APPROVAL_BREACH", "CRAFT_FAILED", "JUDGE_ERROR",
        }),
        opaque=("scripts/bench_craft.py",),
        note="Benchmark回路的分类结果；只出现在评测报告里，不进产品页面。",
    ),
    "replay": VerdictChannel(
        key="replay",
        field="scripts/bench_replay.py replay report verdict",
        owners=("scripts/bench_replay.py",),
        scale=frozenset({"COMPLIANT", "REGRESSION", "NON_REPRODUCIBLE"}),
        opaque=("scripts/bench_replay.py",),
    ),
    # ── local classifications and standalone reports ────────────────────────
    "cache_check": VerdictChannel(
        key="cache_check",
        field="sandbox/cache_verify.py CacheCheck.verdict",
        owners=("sandbox/cache_verify.py",),
        scale=frozenset({"use", "fail", "rebuild"}),
        note="缓存判定，域在 CacheCheck 的 docstring 里另行说明。",
    ),
    "repo_safety": VerdictChannel(
        key="repo_safety",
        field="agent/repo_safety.py file-name classification",
        owners=("agent/repo_safety.py",),
        scale=frozenset({"forbidden", "template"}),
        opaque=("agent/repo_safety.py",),
        note=(
            "本地变量 verdict，不是持久化字段，但同样会被读成「判定」：分类器 "
            "(`_classify_file_name`) 返回的词是运行时算出来的。"
        ),
    ),
    "script_report": VerdictChannel(
        key="script_report",
        field="self-contained report field of standalone scripts",
        owners=("scripts/p0_5_closed_loop.py", "scripts/provider_smoke.py"),
        scale=frozenset({"PENDING", "PASS", "FAIL"}),
        opaque=("scripts/p0_5_closed_loop.py",),
        note=(
            "These two scripts write `verdict` into their own report dict; they "
            "are not the product's summary and must not be counted as job "
            "verdicts. `p0_5_closed_loop.py` is opaque because it also nests a "
            "second, differently-valued `blocker_check[\"verdict\"]` "
            "(BLOCKER / MAJOR) inside the same file — a nested record, not a "
            "word of this scale."
        ),
    ),
    "drill_report": VerdictChannel(
        key="drill_report",
        field="ops drill log verdict",
        owners=(
            "scripts/drill_outbox_crash.py",
            "scripts/drill_provider_outage.py",
            "scripts/drill_worker_kill.py",
        ),
        scale=frozenset(),
        opaque=(
            "scripts/drill_outbox_crash.py",
            "scripts/drill_provider_outage.py",
            "scripts/drill_worker_kill.py",
        ),
        note=(
            "Drill verdicts are prose composed at runtime (\"PASS — crash-window "
            "replay deduplicated, job executed exactly once\"), so no static word "
            "belongs to the scale: an empty scale is the honest declaration."
        ),
    ),
    # ── channels whose authority lives elsewhere ────────────────────────────
    "feedback": VerdictChannel(
        key="feedback",
        field="finding_feedback.verdict (one vote per reviewer)",
        owners=("api/routes/feedback.py", "storage/mysql.py"),
        scale=frozenset({"accept", "reject"}),
        witnesses={
            "accept": "api/routes/feedback.py:44",
            "reject": "api/routes/feedback.py:44",
        },
        source="api.routes.feedback::pattern",
        opaque=("api/routes/feedback.py", "storage/mysql.py"),
        note="Declared by the pydantic `pattern=` on the request model (#81).",
    ),
    "gates": VerdictChannel(
        key="gates",
        field="gate entry status / gates.overall",
        owners=(),
        scale=frozenset({"passed", "failed", "skipped", "error"}),
        source="craft.gates::GateStatus",
        note="门禁通道；`gates.overall` reuses the same words minus `skipped`.",
    ),
    "job_status": VerdictChannel(
        key="job_status",
        field="jobs.status (the state machine, not a verdict)",
        owners=(),
        scale=frozenset({
            "PENDING", "QUEUED", "RUNNING", "WAITING_FOR_PROVIDER", "FAILED",
            "STALE", "VERIFIED", "BLOCKED", "CANCELLED", "ERROR",
        }),
        source="storage.mysql::_VALID_TRANSITIONS",
        note=(
            "Declared here because the Web headline gloss used to be the only "
            "place STALE was spelled, which is how status words ended up in a "
            "verdict vocabulary. `STATUS_HELP` in JobDetail.tsx and the "
            "`?status=` filter in api/routes/jobs.py are still checked against "
            "this channel by hand — see DRILLS for the three words they disagree "
            "on (UNVERIFIED, INCONCLUSIVE, STALE)."
        ),
    ),
}


def owners() -> set[str]:
    """Every file that may mention a verdict field, across all channels."""
    return {path for channel in CHANNELS.values() for path in channel.owners}
