"""Execution loop (design doc §4.4 + 附录 B): plan -> execute -> verify.

For each plan step the success_criteria is evaluated mechanically:
  compile    -> python -m compileall -q on the target files, exit code 0
  test_green -> python -m pytest -q on the workspace, exit code 0
  grep       -> value="" = readability check over target_files; a non-empty
                value must occur in every target file

A failing step enters the diagnose-fix iteration:
- M1: a deterministic "expected/actual" rule template extracts the
  comparison from the failure output, then an EXPLICITLY INJECTED fix rule
  (registry / --fix-module) is applied. Without an injected fix the step
  fails honestly — it never invents one.
- M2: with an LLMClient, the diagnose template asks the model for a JSON
  edit proposal (apply_edit / write_file); every operation still goes
  through Editor (uniqueness / atomic write / backup / audit). An illegal
  or unparseable proposal fails the step with M1 semantics — never faked.
  A token-budget overrun (BudgetExceeded) becomes an honest FAILED.

The same error signature three times in a row marks the step stuck and the
task STUCK. Iteration / tool-call / time / token budgets stop the loop as
FAILED / EXPIRED with the reason on record. reasoning_content (ADR-017)
stays in memory only — it never reaches checkpoint.json / report.json.

checkpoint.json gains one entry per iteration (atomically rewritten);
report.json is the terminal artifact (schema per 附录 B); resume continues
after the last green step recorded in checkpoint.json.

Task memory (卷 XXI §21.1): the loop keeps a TaskMemory of deterministic
facts — file reads (grep criteria), file writes (edited paths), error
signatures (failed iterations, merged by count), decisions (green/stuck/
terminal verdicts) and budget snapshots. It is written to memory.json
alongside every checkpoint, restored by from_checkpoint, and injected into
the diagnose prompt's variable_data section only (never the stable prefix).
Ctrl-C support (卷 XXI §21.3): interrupt_checkpoint() flushes the in-flight
step as an 'interrupted' checkpoint entry + memory.json; report.json stays
untouched until the task actually finishes. All artifacts
(checkpoint/report/memory) carry no reasoning text (ADR-017).

M3 self-verify (SPECCRAFT_PLAN §4.5): _finish runs craft.verify.self_verify
over the changed files before writing report.json (secret/canary scan +
Java contract checkers, both read-only). A failed gate overrides a DONE
verdict to FAILED with the findings on record; edits are NOT rolled back —
the report says so honestly. --no-self-verify (skip_self_verify=True)
skips the gate and marks report.self_verify.status=skipped.

W113 hardening (real eval evidence docs/eval/swebench-llm-results-v3.json):
- edit anchor (flask-4045): the diagnose/edit-proposal prompt ships the
  current real content of each candidate source file (up to 2000 lines,
  raw) and instructs the model to quote old strings EXACTLY from it;
  Editor.apply_edit additionally retries a whitespace-normalized line
  match (tabs collapsed, trailing spaces stripped) before rejecting.
- verify target (flask-4992): "assertion appears" grep criteria search
  SOURCE files only — the harness applies hidden tests AFTER craft, so a
  grep against tests/** can never pass; test-only targets FAIL honestly.

W114 hardening (real eval evidence docs/eval/swebench-llm-results-v4.json):
- verify criterion rebuild (flask-4045 STUCK at verify): a degenerate grep
  assertion value (length < 3 or punctuation-only, e.g. '.'/'..'/'x') is
  dropped and the criterion is rebuilt from problem-statement keywords
  (identifier nouns like url_prefix/prefix/route); the rebuilt criterion
  searches SOURCE files only, and when no usable criterion can be built
  the verify step fails honestly with an 'unverifiable' reason WITHOUT
  entering the diagnose loop — it never counts as a repeated identical
  failure, so the 3x stuck rule stays reserved for real failures.
- anchor cap + anchor repair (flask-4992): the FILE CONTENT ANCHOR ships
  up to 2000 lines of each candidate source file, and an apply_edit
  anchor rejection arms exactly ONE repair round-trip whose instruction
  carries up to 3 real candidate anchor lines (with line numbers) from
  the target file so the retry can quote them exactly.

W143 hardening (real eval evidence docs/eval/swebench-llm-results-v6.json):
- mentioned-path suffix resolution (flask-4045 STUCK s1 understand): a
  mentioned candidate path that does not exist as-is resolves to the ONE
  real workspace file whose path ends with it (normalized / vs \\, e.g.
  'flask/blueprints.py' -> 'src/flask/blueprints.py') — applied to the
  grep-criteria file reads, the diagnose-context anchor reads and the
  candidate-file union through one shared resolver; zero or multiple
  suffix candidates keep the honest failure naming the candidates found.
- understand-stage criterion rebuild (flask-4992 STUCK s2 understand): a
  grep criterion whose targets are all test files (or whose assertion
  value is degenerate/short) is rebuilt at the understand stage through
  the same W114 path as verify — degenerate/short values dropped,
  problem-statement keywords searched over source-only candidate files
  (the extended union). An unbuildable criterion stays an honest
  'unverifiable' failure that never enters the diagnose loop — no stuck
  increment, never a fake pass.

W163 hardening (real eval evidence docs/eval/swebench-llm-results-v10.json):
- transient-timeout retry (flask-4045 FAILED s5, APITimeoutError): the LLM
  client retries a transient gateway timeout (APITimeoutError /
  TimeoutError / 'Request timed out' text) exactly twice with short
  backoff before surfacing LLMUnavailableError; every retry is recorded
  (report.llm_usage.timeout_retries + report.llm_timeout_retries).
- diversified repair retry (flask-4992 STUCK re-proposing one edit): the
  FIRST repeated proposal arms exactly ONE diversified retry — the next
  diagnose call carries an instruction that lists up to 3 canonical
  per-edit summaries of earlier proposals and forbids repeating any of
  them (propose a DIFFERENT fix path). A diversified retry that comes back
  identical falls back to the W156/W158 repeat counting
  ([LLM_PROPOSAL_REPEATED] -> 同类错误连续 3 次 -> STUCK); the
  no-producer paths (cache hit, envelope mode) keep the bare W156
  rejection.

W156 hardening (real eval evidence docs/eval/swebench-llm-results-v9.json):
- test-step scoping + collection tolerance (flask-4045 STUCK s3): in the
  LLM path the test_green step runs pytest scoped to the real workspace
  test files referenced by the spec (or, failing that, the latest
  diagnosis) and always with --continue-on-collection-errors, so an
  unrelated collection error (the old commit's tests/test_cli.py under the
  modern venv pytest) can no longer abort the whole-suite fallback run.
  The deterministic path command stays byte-identical.
- repeated-proposal guard (flask-4992 FAILED s6 迭代预算超限): every
  validated edit proposal is canonicalized (ops sorted by
  (action, path, old, new)) and remembered per loop run; an exact repeat
  fails the step with the stable code [LLM_PROPOSAL_REPEATED] naming the
  iteration that first attempted it, without executing the repeat or
  making another LLM call — the budget is preserved for genuinely new
  attempts.

W35 gate composition + durable job projection: when the M3 self-verify gate
runs at finish, the full GatePipeline (craft/gates.py, five layered gates)
runs too and its summary is embedded as report.gates — informational only,
the loop does NOT block on it here (craft/accept.py owns the hard closure).
An optional AgentJobStore (storage/agent_jobs.py, W30) turns the loop into
a durable, leaseable job: create/lease on start, renew + set_progress per
step, update_status(result_json=report) at finish, supervisor cancel wins
over a leased worker (CANCELLED terminal is flushed honestly), and
from_checkpoint re-leases per the W30 Integration note. store=None keeps
the original in-memory behavior untouched.

W44 metrics wiring (additive, all OFF by default): an optional
ToolCallSelfCheck validates the M2 JSON Action Envelope through
check_with_retry with the model round-trip injected as the producer
callable (an invalid envelope is never executed; a second invalid one
gives up with the stable registry code); an optional ModelRouter routes
the diagnose path via route("diagnose") with one strong fallback on a
cheap-tier failure; an optional SemanticCache serves cacheable diagnose
prompts; judge_persona=True appends the no-fake-pass persona to the
diagnose system block. All counters land in report.gains (tool-call
attempts/valid/retried/success rate, router fallbacks, cache hits,
judge-persona flag) — zero-filled when nothing is configured.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import socket
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from providers.base import LLMMessage, LLMResponse
from providers.budget import BudgetExceeded
from providers.judge_persona import build_judge_prompt
from providers.prompt_templates import (
    JSON_ACTION_ENVELOPE_BLOCK,
    SYSTEM_BLOCK,
    TOOL_SCHEMA_BLOCK,
    assemble,
)
from providers.router import ModelRouter, ProviderRoute
from providers.semantic_cache import SemanticCache, cache_key, cacheable
from providers.toolcheck import (
    CODE_PROPOSAL_INVALID,
    EditProposalSelfCheck,
    ProposalParseFailure,
    ToolCallSelfCheck,
    is_test_file_path,
)
from storage.agent_jobs import (
    AgentJobStore,
    InvalidJobTransitionError,
    JobAlreadyExistsError,
    JobStatus,
)

from .budget import Budget
from .editor import MAX_READ_LINES, EditError, Editor
from .executor import ExecResult, Executor, extract_pytest_failed_tests
from .gates import GatePipeline
from .llm import (
    LLMClient,
    LLMUnavailableError,
    extract_json_object,
    resolve_craft_thinking,
    wrap_data_section,
)
from .memory import MemoryError, TaskMemory
from .planner import CraftPlanError, Plan, Step, classify_task, write_json_atomic
from .schemas import ChangeBundle
from .spec import TaskSpec
from .tools import ToolRegistry
from .verify import self_verify

FixFunction = Callable[[Editor, Step, str], list[str]]


def _prompt_digest(text: str) -> str:
    """sha256 digest of a built prompt (semantic-cache key material)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_job_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"craft-{stamp}-{secrets.token_hex(4)}"


class CraftLoopError(RuntimeError):
    """Loop state or artifact is unusable."""


class _GateError(Exception):
    """Internal budget gate carrying the terminal outcome and reason."""

    def __init__(self, outcome: str, reason: str) -> None:
        super().__init__(reason)
        self.outcome = outcome
        self.reason = reason


class _LLMFixError(RuntimeError):
    """The model's edit proposal was illegal or was refused by the Editor."""


class _ProposalRepeatError(RuntimeError):
    """A validated edit proposal identical to an earlier one (W156).

    The step fails with the stable code [LLM_PROPOSAL_REPEATED] naming the
    iteration that first attempted the proposal — the repeat is neither
    executed again nor sent to the model, so the iteration budget stays
    available for genuinely new attempts.
    """

    def __init__(self, first_iteration: int) -> None:
        super().__init__(
            f"[LLM_PROPOSAL_REPEATED] 编辑提案与第 {first_iteration} 次迭代的提案完全相同 — "
            "重复提案不再执行, 也不再发起 LLM 调用 (预算留给真正的新尝试)"
        )


class _AnchorRejectError(Exception):
    """An apply_edit/apply_patch op whose old-string anchor was rejected.

    Carries the op path, the rejected old string and the exact rejection
    message so the caller can arm exactly ONE repair round-trip whose
    instruction quotes real candidate anchor lines (W114).
    """

    def __init__(self, path: str, old: str, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.old = old
        self.message = message


_EDITOR_API_BLOCK: str = """\
可用编辑工具 (所有路径相对仓库根; 绝对路径与 .. 逃逸会被拒绝):
- read_file(path) -> 带行号内容 (目标文件内容已随本提示提供, 通常无需再读);
- write_file(path, content): 整文件原子写 (temp + replace), 已有文件先备份到 .specraft/backup/;
- apply_edit(path, old, new): 精确子串替换; old 必须在文件中恰好出现一次, 否则拒绝且不落盘;
每次编辑都会写入审计日志 (谁/何时/动了什么)。禁止修改测试文件与 spec 明令禁止的文件。
"""

_EDIT_OPS_SCHEMA: str = """\
OUTPUT CONTRACT — respond with exactly one JSON object (no markdown fences,
no prose around the JSON):

{
  "diagnosis": "one sentence: the root cause you identified from the evidence",
  "edits": [
    {"action": "apply_edit", "path": "calc.py", "old": "return x / 2", "new": "return x * 2"},
    {"action": "write_file", "path": "new.py", "new": "full file content"}
  ]
}

Hard rules:
- action is exactly "apply_edit" or "write_file";
- apply_edit requires old/new strings and old must match EXACTLY once in the
  current file content shown above, otherwise the edit is rejected;
- propose only edits the evidence justifies; never touch test files or
  forbidden files; never invent evidence.
"""

# System-prefix output contract for the diagnose-fix call (首跑缺口修复).
# The gateway only honors response_format=json_object when the prompt
# itself names JSON (docs/design/GRAND_PLAN_V2.md), and the previous prompt
# carried a CONFLICTING JSON Action Envelope tail — the model then answered
# with {"action": ...} envelopes that lacked the "edits" array. This block
# is the single authoritative contract in the stable prefix, with a compact
# inline example; the action envelope is NOT appended to this call anymore.
_EDIT_PROPOSAL_OUTPUT_BLOCK: str = (
    """\
EDIT PROPOSAL OUTPUT CONTRACT — your ENTIRE reply must be ONE JSON object
(no markdown fences, no prose around the JSON) with exactly two top-level
keys: "diagnosis" (string, one sentence naming the root cause) and "edits"
(array of edit operations). Compact example:
"""
    + '{"diagnosis": "double() divides instead of multiplying", "edits": '
    '[{"action": "apply_edit", "path": "src/calc.py", '
    '"old": "return x / 2", "new": "return x * 2"}]}\n'
    + """\
Hard rules:
- each edit object has "action" (exactly "apply_edit" or "write_file") and
  a repo-relative "path";
- apply_edit requires string "old"/"new"; quote old strings EXACTLY from
  the file content above — copy the real lines byte-for-byte (indentation
  and inline whitespace included), never reconstruct code from memory; old
  must match EXACTLY once in the current file content, otherwise the edit
  is rejected;
- write_file requires string "new" (the full file content);
- fix only production/source code, never create or modify test files —
  hidden tests are applied by the harness itself;
- propose only edits the evidence justifies; never touch test files or
  forbidden files; never invent evidence.
"""
)


@dataclass
class StepState:
    step: Step
    status: str = "pending"  # pending | green | failed | stuck
    iterations: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.step.id,
            "kind": self.step.kind,
            "status": self.status,
            "iterations": self.iterations,
            "evidence": dict(self.evidence),
        }


_ASSERT_EQ_RE = re.compile(r"^\s*E\s+assert\s+(.+?)\s*==\s*(.+?)\s*$", re.MULTILINE)

#: Non-alphanumeric characters that make a grep assertion value degenerate
#: when they are all it contains (W114): grepping for "." / "==" / "->"
#: can never attest a fix, so such values are dropped and rebuilt.
_PUNCTUATION: frozenset[str] = frozenset(
    ".,;:()[]{}'\"!?-_=/\\<>|+*&^%$#@~`。，、；：！？…—（）【】《》"
)

#: Common connective/boilerplate tokens that are never fix-relevant nouns
#: (W114 keyword rebuild); any token containing "test" is dropped too.
_VERIFY_CRITERION_STOPWORDS: frozenset[str] = frozenset(
    {
        "about",
        "above",
        "add",
        "after",
        "again",
        "against",
        "all",
        "also",
        "and",
        "are",
        "because",
        "been",
        "before",
        "below",
        "between",
        "both",
        "call",
        "calls",
        "can",
        "case",
        "cases",
        "change",
        "changes",
        "code",
        "could",
        "currently",
        "does",
        "doing",
        "during",
        "each",
        "ensure",
        "ensures",
        "error",
        "errors",
        "every",
        "example",
        "expected",
        "fail",
        "fails",
        "file",
        "files",
        "fix",
        "for",
        "from",
        "function",
        "functions",
        "get",
        "gets",
        "given",
        "has",
        "have",
        "hidden",
        "how",
        "instead",
        "into",
        "issue",
        "issues",
        "like",
        "make",
        "makes",
        "may",
        "might",
        "must",
        "need",
        "needs",
        "not",
        "only",
        "pass",
        "passes",
        "return",
        "returns",
        "set",
        "sets",
        "shall",
        "should",
        "such",
        "than",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "true",
        "use",
        "used",
        "using",
        "value",
        "values",
        "via",
        "want",
        "wants",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "while",
        "who",
        "will",
        "with",
        "would",
    }
)

#: Anchor-content budget for the diagnose prompt (W114): up to 2000 lines
#: per candidate source file, or 60k chars, whichever binds first.
_ANCHOR_CHAR_CAP = 60_000

#: How many real candidate anchor lines an anchor repair instruction shows.
_MAX_ANCHOR_CANDIDATES = 3

#: How many earlier proposals the W163 diversified repair instruction lists.
_MAX_DIVERSIFY_SUMMARIES = 3

#: Per-edit string clip inside a W163 canonical proposal summary.
_EDIT_SUMMARY_CLIP = 100

#: Bounded deterministic workspace scan for the rebuilt verify criterion.
_SOURCE_SCAN_CAP = 50
_SOURCE_SCAN_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".specraft",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "target",
        "venv",
    }
)


def _is_degenerate_assertion_value(value: str) -> bool:
    """True when a grep assertion value cannot meaningfully verify anything.

    Degenerate values (shorter than 3 chars after stripping, or made of
    punctuation only — '.', '..', 'x', '==' ...) are the product of the
    planner extracting a stray token from the problem statement; grepping
    for them can never attest the fix, so the verify criterion must be
    rebuilt from real problem-statement keywords (W114).
    """
    stripped = value.strip()
    if len(stripped) < 3:
        return True
    return all(ch in _PUNCTUATION or ch.isspace() for ch in stripped)


#: A repo-path mention naming a test module (test_*.py / *_test.py under any
#: directory) — W156 uses it to scope the LLM-path pytest run to the test
#: files the spec / diagnosis actually references.
_TEST_PATH_MENTION_RE = re.compile(r"[\w./\\-]+(?:test_[\w-]+|[\w-]+_test)\.py")


def _normalize_mentioned_path(mentioned: str) -> str:
    """Normalize a mentioned workspace path for matching (W143).

    Surrounding quotes/brackets/commas, leading './' and Windows
    backslashes are stripped, so 'flask\\blueprints.py' and
    './flask/blueprints.py' both normalize to 'flask/blueprints.py'.
    """
    return (
        mentioned.strip()
        .strip('`"\'()[],<>;:')
        .replace("\\", "/")
        .lstrip("./")
    )


def _resolve_mentioned_path(
    mentioned: str, files: list[str]
) -> tuple[str | None, list[str]]:
    """Resolve a mentioned path against a scoped list of real workspace files.

    Returns (resolved, suffix_candidates) (W143):
    - an as-is match (after normalization) resolves to itself;
    - otherwise EXACTLY ONE file ending with the mentioned path as a path
      suffix resolves to that file ('flask/blueprints.py' ->
      'src/flask/blueprints.py');
    - zero or multiple suffix matches resolve to None, and the caller keeps
      the honest failure with suffix_candidates naming every file found.
    Callers scope `files` (source-only / all workspace files) so the helper
    can never fabricate a file that does not exist in the workspace.
    """
    cleaned = _normalize_mentioned_path(mentioned)
    if not cleaned:
        return None, []
    if cleaned in files:
        return cleaned, []
    matches = [item for item in files if item.endswith("/" + cleaned)]
    if len(matches) == 1:
        return matches[0], []
    return None, matches


def diagnose_failure(step: Step, result: ExecResult | None, note: str = "") -> str:
    """Deterministic diagnosis rule templates (expected/actual extraction).

    M1 never pretends to reason: it only extracts a comparison from real
    failure output through fixed regex templates and falls back to the
    output tail.
    """
    tail = result.output_tail if result is not None else ""
    match = _ASSERT_EQ_RE.search(tail)
    if match:
        actual = match.group(1).strip()
        expected = match.group(2).strip()
        return f"[规则模板] pytest 断言失败 — 预期值 == 实际值: assert {actual} == {expected}"
    for pattern, label in (
        (r"SyntaxError:\s*(.+)", "语法错误"),
        (r"(?:ModuleNotFoundError|ImportError):\s*(.+)", "导入错误"),
        (r"NameError:\s*(.+)", "名称错误"),
        (r"AssertionError(?::\s*(.+))?", "断言失败"),
    ):
        found = re.search(pattern, tail)
        if found:
            detail = found.group(1).strip() if found.lastindex else ""
            return f"[规则模板] {label}: {detail}"
    if tail:
        return f"[规则模板] 无更细规则可匹配, 失败输出尾部: {tail[-500:]}"
    return f"[规则模板] 无命令输出 (读取/grep 类检查失败): {note}"


def _parse_edit_ops(data: object) -> tuple[str, list[dict[str, Any]]]:
    """Parse the model's edit proposal: {"diagnosis": str, "edits": [...]}
    or a bare [...] array. Illegal shapes raise _LLMFixError — the step
    then fails with M1 semantics instead of pretending.
    """
    explanation = ""
    if isinstance(data, list):
        ops = data
    elif isinstance(data, dict):
        raw_ops = data.get("edits")
        if not isinstance(raw_ops, list):
            raise _LLMFixError("模型输出缺少 edits 数组")
        ops = raw_ops
        raw_explanation = data.get("diagnosis", data.get("explanation", ""))
        if isinstance(raw_explanation, str):
            explanation = raw_explanation.strip()
    else:
        raise _LLMFixError("模型输出顶层必须是 JSON 对象或数组")
    if not all(isinstance(op, dict) for op in ops):
        raise _LLMFixError("编辑操作数组的元素必须是 JSON 对象")
    return explanation, ops


CanonicalEdit = tuple[str, str, str, str]
ProposalKey = tuple[CanonicalEdit, ...]


def _canonical_proposal(ops: list[dict[str, Any]]) -> ProposalKey:
    """Canonical form of a validated edit proposal (W156).

    Every op becomes (action, path, old, new) — write_file (or any op
    missing old/new) contributes an empty string for the absent fields —
    and the ops are sorted by that 4-tuple, so the same set of edits
    proposed in a different order compares equal. Only the edit set
    counts; diagnosis prose is deliberately ignored.
    """
    canon: list[CanonicalEdit] = []
    for op in ops:
        action = op.get("action")
        path = op.get("path")
        old = op.get("old")
        new = op.get("new")
        canon.append(
            (
                str(action),
                str(path) if isinstance(path, str) else "",
                old if isinstance(old, str) else "",
                new if isinstance(new, str) else "",
            )
        )
    return tuple(sorted(canon))


class CraftLoop:
    """In-memory M1 loop over a deterministic plan (no MySQL — that is M4)."""

    def __init__(
        self,
        spec: TaskSpec,
        plan: Plan,
        workspace: str | Path,
        *,
        budget: Budget | None = None,
        job_id: str | None = None,
        artifact_dir: str | Path | None = None,
        fix_registry: dict[str, FixFunction] | None = None,
        exec_mode: str | None = None,
        exec_timeout: int = 600,
        python: str | None = None,
        started_at: float | None = None,
        now_fn: Callable[[], float] | None = None,
        states: list[StepState] | None = None,
        checkpoint_entries: list[dict[str, Any]] | None = None,
        total_iterations: int = 0,
        exec_calls: int = 0,
        task_key: str | None = None,
        client: LLMClient | None = None,
        memory: TaskMemory | None = None,
        skip_self_verify: bool = False,
        tool_registry: ToolRegistry | None = None,
        # W44 metrics wiring — all off by default; passing a self-check /
        # router / cache in is the only way to change behavior.
        tool_call_self_check: ToolCallSelfCheck | None = None,
        router: ModelRouter | None = None,
        semantic_cache: SemanticCache | None = None,
        judge_persona: bool = False,
        store: AgentJobStore | None = None,
        lease_ttl_seconds: float = 900,
    ) -> None:
        if plan.mode not in ("deterministic", "llm"):
            raise CraftLoopError(f"循环只支持 deterministic|llm 计划 (plan.mode={plan.mode!r})")
        self.spec = spec
        self.plan = plan
        self.workspace = Path(workspace)
        self.budget = budget or Budget.from_env()
        self.job_id = job_id or default_job_id()
        self.artifact_dir = (
            Path(artifact_dir)
            if artifact_dir is not None
            else self.workspace / ".specraft" / "jobs" / self.job_id
        )
        registry = dict(fix_registry or {})
        for key, fix in registry.items():
            if not callable(fix):
                raise CraftLoopError(f"fix_registry[{key!r}] 不是可调用对象")
        self.fix_registry = registry
        self.task_key = task_key or classify_task(spec)
        self.exec_mode = exec_mode
        self.exec_timeout = exec_timeout
        self.now_fn = now_fn or time.time
        self.started_at = started_at if started_at is not None else self.now_fn()
        self.deadline = self.started_at + self.budget.timeout_minutes * 60.0
        self.tool_registry = tool_registry
        if tool_call_self_check is not None and tool_registry is None:
            raise CraftLoopError(
                "tool_call_self_check 需要 tool_registry: "
                "自检通过的信封必须经注册表执行, 不能直接调用编辑器"
            )
        self.tool_call_self_check = tool_call_self_check
        self.router = router
        self.semantic_cache = semantic_cache
        self.judge_persona = judge_persona
        self._judge_persona_applied = 0
        if tool_registry is not None:
            # One editor for the whole job: registry dispatches and the
            # loop's grep reads share the audit trail, so report.diff_stat,
            # the M3 base snapshots and memory.json stay coherent. Callers
            # should bind the registry's editor to the job artifact dir.
            self.editor = tool_registry.editor
        else:
            self.editor = Editor(
                self.workspace,
                backup_dir=self.artifact_dir / "backup",
                audit_path=self.artifact_dir / "audit.jsonl",
            )
        self.executor = Executor(
            self.workspace, mode=exec_mode, timeout=exec_timeout, python=python
        )
        self.states = states or [StepState(step=step) for step in plan.steps]
        if len(self.states) != len(plan.steps):
            raise CraftLoopError("states 数量与计划步骤数不一致")
        self.checkpoint_entries: list[dict[str, Any]] = list(checkpoint_entries or [])
        self.total_iterations = total_iterations
        self.exec_calls = exec_calls
        self.last_green_step = ""
        self.client = client
        self.llm_calls = 0
        # M3 self-verify hard gate: default ON; --no-self-verify skips it
        # and _finish marks report.self_verify.status=skipped honestly.
        self.skip_self_verify = skip_self_verify
        # Task-level fact memory (卷 XXI §21.1): file reads/writes, error
        # signatures, decisions and budget snapshots — deterministic facts
        # only, never reasoning text (ADR-017). Persisted to memory.json.
        self.memory = memory or TaskMemory()
        # In-flight step for the Ctrl-C flush (卷 XXI §21.3).
        self._current_step: Step | None = None
        self._current_state: StepState | None = None
        # Latest diagnosis text (deterministic template or LLM diagnose
        # reply) — the W114 v5 candidate-file union reads path references
        # from it so the rebuilt verify criterion can reach files the plan
        # missed (pallets__flask-4992: src/flask/config.py).
        self._last_diagnosis = ""
        # W156 repeated-proposal guard: canonical form of every validated
        # edit proposal already attempted this loop run, mapped to the
        # iteration that first attempted it. An exact repeat fails the step
        # with the stable code [LLM_PROPOSAL_REPEATED] instead of burning
        # the whole iteration budget on the same proposal (real evidence:
        # pallets__flask-4992 FAILED s6 迭代预算超限).
        self._attempted_proposals: dict[ProposalKey, int] = {}
        # W158 alignment with M1 semantics: consecutive repeats per step are
        # counted like any other identical failure — the 3rd consecutive
        # repeat trips the documented 同类错误连续 3 次 → STUCK rule (with
        # the [LLM_PROPOSAL_REPEATED] signature), never an early FAILED.
        self._repeat_counts: dict[str, int] = {}
        # W163 diversified repair retry: the FIRST repeated proposal arms
        # exactly ONE diversified retry — the next diagnose call carries an
        # instruction that lists earlier proposals (canonical per-edit
        # summaries) and demands a DIFFERENT fix path. Armed in _run_step
        # on the first repeat, consumed by _take_diversification().
        self._diversification_armed: str | None = None
        # W35 durable job projection (W30 AgentJobStore). store=None keeps the
        # original in-memory behavior; the lease owner is computed at run()
        # time (host:pid:job_id) and must not change within one run.
        self.store = store
        self.lease_ttl_seconds = lease_ttl_seconds
        self._lease_owner = ""

    @property
    def tool_calls_used(self) -> int:
        return self.exec_calls + len(self.editor.audit) + self.llm_calls

    # -- gates -----------------------------------------------------------

    def _time_gate(self, state: StepState) -> None:
        if self.now_fn() >= self.deadline:
            reason = (
                f"时间预算超限 ({self.budget.timeout_minutes} 分钟): 任务 deadline 已到, "
                f"已用 {round(self.now_fn() - self.started_at, 1)}s"
            )
            state.evidence["reason"] = reason
            raise _GateError("EXPIRED", reason)

    def _tool_gate(self, state: StepState) -> None:
        if self.tool_calls_used > self.budget.max_tool_calls:
            reason = (
                f"工具调用预算超限 (max_tool_calls={self.budget.max_tool_calls}, "
                f"已用 {self.tool_calls_used})"
            )
            state.evidence["reason"] = reason
            raise _GateError("FAILED", reason)

    # -- loop ------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.plan.save(self.artifact_dir / "plan.json")
        self._store_prepare()
        self._store_lease()
        if self.store is not None:
            # supervisor cancel wins over late projections
            with suppress(InvalidJobTransitionError):
                self.store.set_plan(self.job_id, self.plan.to_dict())
        for index, step in enumerate(self.plan.steps):
            state = self.states[index]
            if state.status == "green":
                continue
            if self._store_cancelled(step):
                return self._finish("CANCELLED")
            self._store_renew()
            try:
                self._time_gate(state)
            except _GateError as gate:
                state.evidence["reason"] = gate.reason
                return self._finish(gate.outcome)
            outcome = self._run_step(step, state)
            if outcome != "green":
                return self._finish(outcome)
        return self._finish("DONE")

    # -- durable job projection (W35 / W30 Integration note) -----------------

    def _store_prepare(self) -> None:
        """Job intake: probe-then-create (create raises on duplicates)."""
        if self.store is None:
            return
        if self.store.get(self.job_id) is None:
            # another worker raced us in; the lease below arbitrates
            with suppress(JobAlreadyExistsError):
                self.store.create(self.job_id, json.dumps(self.spec.to_dict()))

    def _store_lease(self) -> None:
        """Acquire the job lease; refusing to run without it is fail-closed."""
        if self.store is None:
            return
        self._lease_owner = f"{socket.gethostname()}:{os.getpid()}:{self.job_id}"
        if not self.store.lease(self.job_id, self._lease_owner, self.lease_ttl_seconds):
            raise CraftLoopError(
                f"作业 {self.job_id} 租约未获取 (被另一 worker 持有或已是终态); 不重复执行"
            )

    def _store_renew(self) -> None:
        """Renew the lease once per step; losing it to another worker aborts."""
        if self.store is None or not self._lease_owner:
            return
        if self.store.renew(self.job_id, self._lease_owner, self.lease_ttl_seconds):
            return
        job = self.store.get(self.job_id)
        if job is not None and job.status == "cancelled":
            return  # the step-loop cancel check flushes the honest exit
        raise CraftLoopError(f"作业 {self.job_id} 租约失效 (另一 worker 接管或租约过期); 中止")

    def _store_cancelled(self, step: Step) -> bool:
        """Supervisor cancel check: cancel wins even over a leased worker."""
        if self.store is None:
            return False
        job = self.store.get(self.job_id)
        if job is not None and job.status == "cancelled":
            self._checkpoint(
                step_id=step.id,
                iteration=0,
                diagnosis="supervisor 取消作业 (cancel 优先于租约), 本步骤未执行",
                edits_applied=[],
                build_result={"exit_code": -1, "failed_tests": [], "log_tail": ""},
                verdict="cancelled",
            )
            return True
        return False

    def _store_set_progress(self, step_id: str, iteration: int) -> None:
        """Project the current step into the durable store (per checkpoint)."""
        if self.store is None:
            return
        state = self._current_state
        progress: dict[str, Any] = {
            "status": state.status if state is not None else "pending",
            "iterations": state.iterations if state is not None else iteration,
            "evidence": dict(state.evidence) if state is not None else {},
        }
        # supervisor cancel wins over late projections
        with suppress(InvalidJobTransitionError):
            self.store.set_progress(self.job_id, current_step=step_id, progress=progress)

    def _run_step(self, step: Step, state: StepState) -> str:
        self._current_step = step
        self._current_state = state
        try:
            ok, evidence, result = self._check_criteria(step, state)
        except _GateError as gate:
            state.evidence["reason"] = gate.reason
            return gate.outcome
        if ok:
            state.status = "green"
            state.evidence = evidence
            self.last_green_step = step.id
            self.memory.add("decision", f"步骤 {step.id} 首次检查即 green", step_id=step.id)
            self._checkpoint(
                step_id=step.id,
                iteration=0,
                diagnosis="",
                edits_applied=[],
                build_result=self._result_dict(result),
                verdict="green",
            )
            return "green"
        if evidence.get("unverifiable"):
            # W114: an unbuildable verify criterion fails honestly right
            # away — no diagnose loop, so it can never count as a repeated
            # identical failure (the 3x stuck rule stays for real failures).
            return self._fail_unverifiable(step, state, evidence, 0, result)
        attempts = 0
        last_signature = ""
        consecutive = 0
        while True:
            try:
                self._time_gate(state)
            except _GateError as gate:
                state.evidence["reason"] = gate.reason
                return gate.outcome
            if self.total_iterations >= self.budget.max_iterations:
                state.status = "failed"
                reason = f"迭代预算超限 (max_iterations={self.budget.max_iterations})"
                state.evidence["reason"] = reason
                self._checkpoint(
                    step_id=step.id,
                    iteration=attempts,
                    diagnosis=reason,
                    edits_applied=[],
                    build_result=self._result_dict(result),
                    verdict="progress",
                )
                return "FAILED"
            attempts += 1
            self.total_iterations += 1
            diagnosis = diagnose_failure(step, result, note=evidence.get("reason", ""))
            self._last_diagnosis = diagnosis
            fix = self._lookup_fix(step)
            if fix is None:
                if self.client is None:
                    state.status = "failed"
                    if self.plan.mode == "llm":
                        reason = (
                            f"步骤 {step.id} 失败且无注入 fix 规则, 但未提供 LLM 客户端 "
                            "(llm 计划需 --llm 或注入 --fix-module); 不假装智能"
                        )
                    else:
                        reason = (
                            f"M1 确定性模式未注入步骤 {step.id} 的 fix 规则 (--fix-module), "
                            "无法自动修复; 不假装智能"
                        )
                    state.evidence["reason"] = reason
                    self._checkpoint(
                        step_id=step.id,
                        iteration=attempts,
                        diagnosis=diagnosis,
                        edits_applied=[],
                        build_result=self._result_dict(result),
                        verdict="progress",
                    )
                    return "FAILED"
                try:
                    diagnosis, edited = self._llm_fix(step, result, diagnosis)
                    self._last_diagnosis = diagnosis
                except BudgetExceeded as exc:
                    state.status = "failed"
                    reason = f"LLM token 预算超限: {exc}"
                    state.evidence["reason"] = reason
                    self._checkpoint(
                        step_id=step.id,
                        iteration=attempts,
                        diagnosis=diagnosis,
                        edits_applied=[],
                        build_result=self._result_dict(result),
                        verdict="progress",
                    )
                    return "FAILED"
                except LLMUnavailableError as exc:
                    state.status = "failed"
                    reason = "LLM unavailable: " + str(exc)
                    state.evidence["reason"] = reason
                    self._checkpoint(
                        step_id=step.id,
                        iteration=attempts,
                        diagnosis=diagnosis,
                        edits_applied=[],
                        build_result=self._result_dict(result),
                        verdict="progress",
                    )
                    return "FAILED"
                except _LLMFixError as exc:
                    state.status = "failed"
                    reason = f"LLM 编辑提案非法, 按 M1 语义 FAILED: {exc}"
                    state.evidence["reason"] = reason
                    self._checkpoint(
                        step_id=step.id,
                        iteration=attempts,
                        diagnosis=diagnosis,
                        edits_applied=[],
                        build_result=self._result_dict(result),
                        verdict="progress",
                    )
                    return "FAILED"
                except _ProposalRepeatError as exc:
                    # W158 alignment with M1: a repeated proposal counts
                    # like any other identical failure — repeats 1-2
                    # checkpoint progress and retry (the repeat itself is
                    # never executed); the 3rd consecutive repeat trips the
                    # documented 同类错误连续 3 次 → STUCK rule with the
                    # [LLM_PROPOSAL_REPEATED] signature, never an early
                    # FAILED (real evidence: pallets__flask-4992 v9 burned
                    # 12 iterations on the same proposal).
                    repeats = self._repeat_counts.get(step.id, 0) + 1
                    self._repeat_counts[step.id] = repeats
                    # W163: the FIRST repeat arms exactly ONE diversified
                    # retry for the NEXT diagnose call (the instruction is
                    # consumed by _take_diversification, so no extra LLM
                    # call and the W158 counting is untouched). The
                    # no-producer paths (envelope mode) keep the bare
                    # W156 rejection — W161 semantics intact.
                    if repeats == 1 and self.tool_call_self_check is None:
                        self._diversification_armed = step.id
                    reason = str(exc)
                    state.evidence["reason"] = reason
                    if repeats >= 3:
                        state.status = "stuck"
                        state.iterations = attempts
                        state.evidence["reason"] = (
                            f"同类错误连续 {repeats} 次, 判定 stuck "
                            f"(签名: {reason[:160]})"
                        )
                        self.memory.add(
                            "decision",
                            f"步骤 {step.id} stuck: 编辑提案重复 {repeats} 次",
                            step_id=step.id,
                        )
                        self._checkpoint(
                            step_id=step.id,
                            iteration=attempts,
                            diagnosis=diagnosis,
                            edits_applied=[],
                            build_result=self._result_dict(result),
                            verdict="stuck",
                        )
                        return "STUCK"
                    self._checkpoint(
                        step_id=step.id,
                        iteration=attempts,
                        diagnosis=diagnosis,
                        edits_applied=[],
                        build_result=self._result_dict(result),
                        verdict="progress",
                    )
                    continue
            else:
                try:
                    edited = fix(self.editor, step, diagnosis)
                except EditError as exc:
                    edited = []
                    diagnosis = f"[规则模板] fix 函数抛错 (编辑被拒): {exc}"
                if not isinstance(edited, list) or not all(isinstance(p, str) for p in edited):
                    state.status = "failed"
                    state.evidence["reason"] = "fix 函数返回类型错误: 应为 list[str]"
                    return "FAILED"
            try:
                self._tool_gate(state)
                ok, evidence, result = self._check_criteria(step, state)
            except _GateError as gate:
                state.evidence["reason"] = gate.reason
                return gate.outcome
            if ok:
                state.status = "green"
                state.evidence = evidence
                state.iterations = attempts
                self.last_green_step = step.id
                self.memory.add(
                    "decision",
                    f"步骤 {step.id} 修复后 green (迭代 {attempts})",
                    step_id=step.id,
                )
                self._checkpoint(
                    step_id=step.id,
                    iteration=attempts,
                    diagnosis=diagnosis,
                    edits_applied=list(edited),
                    build_result=self._result_dict(result),
                    verdict="green",
                )
                return "green"
            if evidence.get("unverifiable"):
                return self._fail_unverifiable(step, state, evidence, attempts, result)
            signature = self._error_signature(step, result, note=str(evidence.get("reason", "")))
            self.memory.add("error_signature", signature, step_id=step.id)
            if signature == last_signature:
                consecutive += 1
            else:
                last_signature = signature
                consecutive = 1
            rerun_diagnosis = diagnose_failure(step, result, note=evidence.get("reason", ""))
            if consecutive >= 3:
                state.status = "stuck"
                state.iterations = attempts
                state.evidence["reason"] = (
                    f"同类错误连续 {consecutive} 次, 判定 stuck (签名: {signature[:160]})"
                )
                self.memory.add(
                    "decision",
                    f"步骤 {step.id} stuck: 同类错误签名连续 {consecutive} 次",
                    step_id=step.id,
                )
                self._checkpoint(
                    step_id=step.id,
                    iteration=attempts,
                    diagnosis=rerun_diagnosis,
                    edits_applied=list(edited),
                    build_result=self._result_dict(result),
                    verdict="stuck",
                )
                return "STUCK"
            self._checkpoint(
                step_id=step.id,
                iteration=attempts,
                diagnosis=rerun_diagnosis,
                edits_applied=list(edited),
                build_result=self._result_dict(result),
                verdict="progress",
            )

    def _fail_unverifiable(
        self,
        step: Step,
        state: StepState,
        evidence: dict[str, Any],
        iteration: int,
        result: ExecResult | None,
    ) -> str:
        """Honest terminal for an unbuildable verify criterion (W114).

        The step fails immediately with the 'unverifiable' reason on
        record: it never enters the diagnose-fix loop, so the failure can
        never count as a repeated identical error signature (3x stuck
        applies to real failures only).
        """
        reason = str(evidence.get("reason") or "unverifiable")
        state.status = "failed"
        state.iterations = iteration
        state.evidence = dict(evidence)
        self.memory.add(
            "decision",
            f"步骤 {step.id} unverifiable: {reason} (不进入修复循环)",
            step_id=step.id,
        )
        self._checkpoint(
            step_id=step.id,
            iteration=iteration,
            diagnosis=reason,
            edits_applied=[],
            build_result=self._result_dict(result),
            verdict="progress",
        )
        return "FAILED"

    # -- criteria --------------------------------------------------------

    def _check_criteria(
        self, step: Step, state: StepState
    ) -> tuple[bool, dict[str, Any], ExecResult | None]:
        criteria = step.success_criteria
        if criteria.type == "compile":
            if not step.target_files:
                return (
                    True,
                    {"check": "compile", "note": "无目标文件, 跳过编译 (M1 确定性骨架)"},
                    None,
                )
            result = self._exec(["python", "-m", "compileall", "-q", *step.target_files], state)
            evidence: dict[str, Any] = {
                "check": "compile",
                "exit_code": result.exit_code,
                "mode": result.mode,
                "output_tail": result.output_tail,
            }
            if result.stderr.strip():
                evidence["stderr_tail"] = result.stderr[-1000:]
            if result.error:
                evidence["error"] = result.error
            return (result.exit_code == 0, evidence, result)
        if criteria.type == "test_green":
            result = self._exec(self._build_test_step_command(), state)
            # 首跑缺口修复: the real stderr tail and the sandbox-level error
            # (spawn failure / venv python missing / timeout) ride the
            # evidence — a failing run_test must never surface as empty.
            evidence = {
                "check": "test_green",
                "exit_code": result.exit_code,
                "failed_tests": extract_pytest_failed_tests(f"{result.stdout}\n{result.stderr}"),
                "mode": result.mode,
                "output_tail": result.output_tail,
            }
            if result.stderr.strip():
                evidence["stderr_tail"] = result.stderr[-1000:]
            if result.error:
                evidence["error"] = result.error
            return (result.exit_code == 0, evidence, result)
        contents: dict[str, str] = {}
        # 诚实不变量 (W113): 断言值类 grep 校验 ("assertion appears") 只搜索
        # 源文件, 永不搜索测试文件 — 隐藏测试由评测框架在 craft 结束之后才
        # 应用到仓库, craft 阶段根本看不见它们, 因此对 tests/** 的断言值
        # 校验永远无法通过 (真实证据: pallets__flask-4992 在
        # tests/test_config.py 上 grep "tomllib" 3 轮后 STUCK)。目标只有
        # 测试文件时诚实 FAILED, 绝不伪造通过。value="" 的可读性检查不
        # 过滤 (不涉及断言值), 保持原语义。
        # W114 验证标准重建 (pallets__flask-4045 STUCK at verify): 退化的
        # 断言值 (长度 < 3 或纯标点, 如 '.'/'..'/'x') 直接丢弃, 改为从
        # 问题陈述提取关键词并在源文件上 grep; 重建不出可用标准时诚实
        # 报告 unverifiable 且不进入修复循环 (不计入连续同类失败)。
        # W143 (pallets__flask-4992 STUCK s2 understand): understand 阶段
        # 与 verify 走同一重建路径 — 目标全为测试文件的判据 (即使断言值
        # 非退化, 如 'from_file') 同样触发关键词重建; 重建失败则诚实
        # unverifiable, 绝不伪造通过, 不计入连续同类失败。
        value = criteria.value
        targets = step.target_files
        excluded_tests: list[str] = []
        rebuilt_from: str | None = None
        if value:
            excluded_tests = [t for t in step.target_files if is_test_file_path(t)]
            targets = [t for t in step.target_files if not is_test_file_path(t)]
            if _is_degenerate_assertion_value(value) or (not targets and step.target_files):
                rebuilt = self._rebuild_grep_criterion()
                if rebuilt is None:
                    if _is_degenerate_assertion_value(value):
                        reason = self._unverifiable_reason(value)
                    else:
                        reason = self._test_only_unverifiable_reason(
                            value, step.target_files
                        )
                    return (
                        False,
                        {"check": "grep", "unverifiable": True, "reason": reason},
                        None,
                    )
                rebuilt_from = value
                value, targets = rebuilt
        # W143 mentioned-path suffix resolution (flask-4045 s1 understand):
        # a target that does not exist as-is resolves to the ONE real
        # workspace file ending with it ('flask/blueprints.py' ->
        # 'src/flask/blueprints.py'); zero or multiple suffix candidates
        # keep the honest failure naming the candidates found.
        search_files = self._workspace_source_files() if value else self._workspace_py_files()
        resolved_targets: list[str] = []
        for target in targets:
            resolved, suffix_candidates = _resolve_mentioned_path(target, search_files)
            if resolved is None:
                # not an as-is workspace .py file: keep the original honest
                # read error and add the suffix-candidate facts
                try:
                    lines = self.editor.read_file(target)
                except EditError as exc:
                    detail = ""
                    if suffix_candidates:
                        detail = f"; 后缀匹配不唯一: {sorted(suffix_candidates)}"
                    return (
                        False,
                        {"check": "grep", "reason": f"目标文件不可读: {target} ({exc}){detail}"},
                        None,
                    )
                resolved = target
            else:
                try:
                    lines = self.editor.read_file(resolved)
                except EditError as exc:
                    return (
                        False,
                        {"check": "grep", "reason": f"目标文件不可读: {resolved} ({exc})"},
                        None,
                    )
            contents[resolved] = "\n".join(line for _, line in lines)
            if resolved not in resolved_targets:
                resolved_targets.append(resolved)
            self.memory.add("file_read", resolved, step_id=step.id)
        if not value:
            return (
                True,
                {
                    "check": "grep",
                    "note": f"可读性检查通过: {sorted(contents)} (M1 不注入上下文)",
                },
                None,
            )
        if rebuilt_from is not None:
            trigger = (
                "退化"
                if _is_degenerate_assertion_value(rebuilt_from)
                else "无源文件可搜索 (目标均为测试文件)"
            )
            hits = [t for t in resolved_targets if value in contents[t]]
            if not hits:
                reason = (
                    f"断言值 {rebuilt_from!r} {trigger}, 已按问题陈述重建关键词 {value!r}; "
                    f"该关键词未出现在任何候选源文件: {sorted(resolved_targets)}"
                )
                if excluded_tests:
                    reason += (
                        f"; 已排除测试文件 {sorted(excluded_tests)} "
                        "(隐藏测试由评测框架在 craft 后施加, 不做断言校验)"
                    )
                return (False, {"check": "grep", "reason": reason}, None)
            note = (
                f"断言值 {rebuilt_from!r} {trigger}, 已按问题陈述重建关键词 {value!r}; "
                f"命中源文件 {sorted(hits)}"
            )
            if excluded_tests:
                note += (
                    f"; 已排除测试文件 {sorted(excluded_tests)} "
                    "(隐藏测试由评测框架在 craft 后施加, 不做断言校验)"
                )
            return (True, {"check": "grep", "note": note}, None)
        missing = [t for t in resolved_targets if value not in contents[t]]
        if missing:
            reason = f"断言值 {value!r} 未出现在源文件: {missing}"
            if excluded_tests:
                reason += (
                    f"; 已排除测试文件 {sorted(excluded_tests)} "
                    "(隐藏测试由评测框架在 craft 后施加, 不做断言校验)"
                )
            return (False, {"check": "grep", "reason": reason}, None)
        note = f"断言值 {value!r} 命中全部目标源文件 {sorted(contents)}"
        if excluded_tests:
            note += (
                f"; 已排除测试文件 {sorted(excluded_tests)} "
                "(隐藏测试由评测框架在 craft 后施加, 不做断言校验)"
            )
        return (True, {"check": "grep", "note": note}, None)

    # -- test-step pytest command (W156) ------------------------------------

    def _build_test_step_command(self) -> list[str]:
        """The test_green pytest command (W156).

        Deterministic path (no LLM client): byte-identical to the pre-W156
        command. LLM path: --continue-on-collection-errors always, plus
        scoping to the real workspace test files referenced by the spec /
        latest diagnosis when any exist (pallets__flask-4045: the problem
        statement's tests/test_blueprints.py must run instead of the whole
        suite, whose old-commit tests/test_cli.py fails collection under
        the modern venv pytest). No referenced file -> the whole suite
        still runs, but the flag keeps unrelated collection errors from
        aborting it.
        """
        command = ["python", "-m", "pytest", "-q"]
        if self.client is None:
            return command
        command.append("--continue-on-collection-errors")
        referenced = self._referenced_test_files()
        if referenced:
            command.extend(referenced)
        return command

    def _referenced_test_files(self) -> list[str]:
        """Real workspace test files the spec or the latest diagnosis
        references (W156), resolved through the shared suffix resolver.

        Spec references win (the problem statement names the targeted test
        path); only when the spec names no resolvable test file are the
        latest-diagnosis references consulted. Only real workspace files
        are ever returned — a mention that cannot be resolved adds
        nothing, and an empty result means "run the whole suite".
        """
        files = self._workspace_py_files()
        spec_text = " ".join(
            [
                self.spec.title,
                self.spec.description,
                *self.spec.acceptance_criteria,
                self.spec.affected_area_hint,
            ]
        )
        for text in (spec_text, self._last_diagnosis or ""):
            found: list[str] = []
            for mention in _TEST_PATH_MENTION_RE.findall(text):
                cleaned = _normalize_mentioned_path(mention)
                if not is_test_file_path(cleaned):
                    continue
                resolved, _ = _resolve_mentioned_path(cleaned, files)
                if resolved is not None and resolved not in found:
                    found.append(resolved)
            if found:
                return sorted(found)
        return []

    # -- verify criterion rebuild (W114) ------------------------------------

    def _problem_statement_keywords(self) -> list[str]:
        """Deterministic keyword extraction from the problem statement.

        Title + description + acceptance criteria are joined, then
        identifier tokens ([A-Za-z_][A-Za-z0-9_]*) are collected and
        lowercased. Each token is emitted compound-first and then split on
        '_' and inner camelCase boundaries, so url_prefix (or urlPrefix)
        yields url_prefix/url/prefix. Tokens shorter than 3 chars,
        stopwords and anything containing "test" are dropped; first-seen
        order is preserved and de-duplicated.
        """
        text = " ".join([self.spec.title, self.spec.description, *self.spec.acceptance_criteria])
        keywords: list[str] = []
        seen: set[str] = set()
        for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
            candidates: list[str] = [raw.lower()]
            snake_parts = [part for part in raw.split("_") if part]
            candidates.extend(part.lower() for part in snake_parts)
            for part in snake_parts:
                candidates.extend(
                    piece.lower() for piece in re.findall(r"[A-Z]?[a-z]+|[0-9]+", part)
                )
            for token in candidates:
                if len(token) < 3 or token in seen:
                    continue
                if token in _VERIFY_CRITERION_STOPWORDS or "test" in token:
                    continue
                seen.add(token)
                keywords.append(token)
        return keywords

    def _workspace_py_files(self) -> list[str]:
        """Every .py file in the workspace (uncapped, scan skips), tests included.

        The source-only view filters through is_test_file_path; callers that
        legitimately read test files (value="" readability checks) use this
        list directly so as-is mentioned paths still resolve.
        """
        found: list[str] = []
        for path in self.workspace.rglob("*.py"):
            relative = path.relative_to(self.workspace)
            if any(part in _SOURCE_SCAN_SKIP_DIRS for part in relative.parts):
                continue
            found.append(relative.as_posix())
        return sorted(found)

    def _workspace_source_files(self) -> list[str]:
        """Every non-test .py file in the workspace (uncapped, scan skips)."""
        return [item for item in self._workspace_py_files() if not is_test_file_path(item)]

    def _scan_source_files(self) -> list[str]:
        """Bounded deterministic scan for non-test .py files in the workspace."""
        return self._workspace_source_files()[:_SOURCE_SCAN_CAP]

    def _resolve_source_reference(self, reference: str, files: list[str]) -> list[str]:
        """Real non-test workspace files matching a path reference (W143).

        The reference may be a full workspace-relative path
        ('src/flask/config.py') or a suffix ('flask/config.py'); it is
        resolved through the shared _resolve_mentioned_path resolver — an
        as-is match wins, a UNIQUE path-suffix match resolves, and an
        absent or ambiguous suffix adds nothing. Every returned file is a
        real file in `files`, so the candidate union can never fabricate
        or guess a source file (W114 no-fake-pass invariant) and never
        names a test file.
        """
        resolved, _ = _resolve_mentioned_path(reference, files)
        return [resolved] if resolved is not None else []

    def _candidate_references(self) -> list[str]:
        """Path references for the candidate union, in deterministic order.

        The SPEC's affected_area_hint tokens first (comma/whitespace
        separated, exactly as the planner splits them), then every .py
        path mentioned in the latest diagnosis text (the diagnose reply).
        """
        references: list[str] = []
        hint = self.spec.affected_area_hint.strip()
        if hint:
            references.extend(token for token in re.split(r"[,\s，、]+", hint) if token)
        if self._last_diagnosis:
            references.extend(re.findall(r"[\w./\\-]+\.py\b", self._last_diagnosis))
        return references

    def _candidate_source_files(self) -> list[str]:
        """Source files the rebuilt verify criterion may grep.

        The union of every plan step's non-test target files (the files
        craft is actually allowed to edit), the SPEC's affected_area_hint
        files and the files referenced in the latest diagnosis text — the
        latter two resolved to real non-test workspace files (W114 v5:
        pallets__flask-4992's src/flask/config.py was absent from the
        union at verify time, so the rebuilt 'tomllib' keyword scan had no
        source file to reach). When the union carries no source file at
        all, falls back to a bounded deterministic scan of the workspace's
        non-test .py files.
        """
        candidates: set[str] = set()
        for plan_step in self.plan.steps:
            for target in plan_step.target_files:
                if not is_test_file_path(target):
                    candidates.add(target)
        files = self._workspace_source_files()
        for reference in self._candidate_references():
            candidates.update(self._resolve_source_reference(reference, files))
        if candidates:
            return sorted(candidates)
        return self._scan_source_files()

    def _rebuild_grep_criterion(self) -> tuple[str, list[str]] | None:
        """Rebuild a degenerate grep criterion from the problem statement.

        Returns (keyword, source_targets) when a usable criterion can be
        built — the first keyword (in extraction order) that occurs in at
        least one candidate source file, else the first keyword — or None
        when no keyword can be extracted or no source file exists to
        search (the honest 'unverifiable' case).
        """
        keywords = self._problem_statement_keywords()
        if not keywords:
            return None
        targets = self._candidate_source_files()
        if not targets:
            return None
        choice = keywords[0]
        found = False
        for keyword in keywords:
            for target in targets:
                try:
                    lines = self.editor.read_file(target)
                except EditError:
                    continue
                if any(keyword in line for _, line in lines):
                    choice = keyword
                    found = True
                    break
            if found:
                break
        return choice, targets

    def _unverifiable_reason(self, value: str) -> str:
        """Honest reason for a verify criterion that cannot be rebuilt (W114)."""
        keywords = self._problem_statement_keywords()
        sources = self._candidate_source_files()
        if not keywords:
            return (
                f"unverifiable: 断言值 {value!r} 退化 (长度<3 或纯标点), "
                "且无法从问题陈述提取可用关键词 — 验证标准无法重建, "
                "不进入修复循环, 不计入连续同类失败"
            )
        return (
            f"unverifiable: 断言值 {value!r} 退化, 已提取关键词 {keywords[:5]}, "
            f"但工作区无任何可搜索的源文件 ({len(sources)} 个候选) — "
            "验证标准无法重建, 不进入修复循环, 不计入连续同类失败"
        )

    def _test_only_unverifiable_reason(self, value: str, original_targets: list[str]) -> str:
        """Honest reason when a criterion whose targets are all test files
        cannot be rebuilt from the problem statement (W143 flask-4992 s2
        understand): the step fails unverifiable without entering the
        diagnose loop, so it never counts as a repeated identical failure.
        """
        return (
            f"unverifiable: 断言值 {value!r} 无源文件可搜索: 目标 "
            f"{sorted(original_targets)} 均为测试文件, 且按问题陈述重建验证标准失败 — "
            "不进入修复循环, 不计入连续同类失败"
        )

    def _exec(self, command: list[str], state: StepState) -> ExecResult:
        self._time_gate(state)
        self.exec_calls += 1
        self._tool_gate(state)
        return self.executor.run(command, timeout=self.exec_timeout)

    # -- diagnosis / fix ---------------------------------------------------

    def _lookup_fix(self, step: Step) -> FixFunction | None:
        for key in (step.id, step.kind, self.task_key, "*"):
            candidate = self.fix_registry.get(key)
            if candidate is not None:
                return candidate
        return None

    def _llm_fix(
        self, step: Step, result: ExecResult | None, diagnosis: str
    ) -> tuple[str, list[str]]:
        """M2 diagnose-fix: the model proposes JSON edit operations — or,
        with a ToolCallSelfCheck configured, one validated JSON Action
        Envelope — and the Editor enforces uniqueness / atomic write /
        backup / audit exactly as in M1. Returns (diagnosis_text,
        edited_paths).

        W44 wiring, all OFF by default (an unconfigured loop behaves
        identically to the pre-W44 one):
        - judge_persona=True appends the no-fake-pass judge persona to the
          diagnose system block;
        - a router routes the diagnosis path via router.route("diagnose")
          and a cheap-tier failure falls back to one strong retry (the
          router counts it);
        - a semantic cache serves cacheable diagnose prompts and skips the
          LLM round-trip on a hit;
        - a ToolCallSelfCheck forces the envelope output contract and runs
          the model round-trip through check_with_retry with the producer
          callable injected — an invalid envelope is never executed.

        Raises _LLMFixError for illegal output, BudgetExceeded for token
        overruns and LLMUnavailableError when no route exists — the caller
        converts each into an honest FAILED.
        """
        client = self.client
        if client is None:
            raise LLMUnavailableError("LLM 客户端未提供 (诊断-修复需要 --llm)")
        envelope_mode = self.tool_call_self_check is not None
        # The edit-proposal contract is the ONLY output contract of the
        # non-envelope diagnose call: the JSON Action Envelope tail is not
        # appended here anymore (it previously competed with the edits
        # schema and the model answered with {"action": ...} envelopes that
        # lacked the "edits" array — 首跑缺口 pallets__flask-4045).
        base = (
            SYSTEM_BLOCK + "\n\n" + TOOL_SCHEMA_BLOCK
            if envelope_mode
            else SYSTEM_BLOCK + "\n\n" + _EDIT_PROPOSAL_OUTPUT_BLOCK
        )
        if self.judge_persona:
            base = build_judge_prompt(base)
            self._judge_persona_applied += 1
        context = self._diagnose_context(step, result, diagnosis, envelope_mode=envelope_mode)
        if envelope_mode:
            return self._llm_fix_envelope(client, base, context, step, diagnosis)
        built = assemble(base, "diagnose", context, include_envelope=False)
        route = self.router.route("diagnose") if self.router is not None else None
        cached: dict[str, Any] | None = None
        cache_key_value = ""
        if self.semantic_cache is not None and cacheable("diagnose"):
            model = route.model if route is not None else ""
            cache_key_value = cache_key(
                _prompt_digest(built.text),
                model,
                {"step_id": step.id, "envelope": False},
            )
            hit = self.semantic_cache.get(cache_key_value)
            if isinstance(hit, dict) and isinstance(hit.get("ops"), list):
                cached = hit
        if cached is None:
            # EditProposalSelfCheck (ToolCallSelfCheck pattern): an invalid
            # or unparseable proposal arms exactly ONE deterministic repair
            # instruction; a second invalid proposal gives up carrying the
            # stable code LLM_PROPOSAL_INVALID.
            checker = EditProposalSelfCheck()
            # W163: the ONE armed diversified retry rides the first call of
            # this invocation (only when the checker passes no repair
            # instruction of its own — the checker's repair still wins).
            diversification = self._take_diversification(step)

            def produce(instruction: str | None) -> object:
                effective = instruction if instruction is not None else diversification
                text = built.text if effective is None else f"{built.text}\n\n{effective}"
                response = self._diagnose_call(
                    client,
                    [LLMMessage(role="user", content=text)],
                    step,
                    text,
                    route,
                )
                content = response.content or ""
                try:
                    return extract_json_object(content)
                except (json.JSONDecodeError, TypeError, ValueError):
                    snippet = content.strip() or "(空输出)"
                    return ProposalParseFailure(snippet[-240:])

            outcome = checker.check_with_retry(produce)
            if outcome.status != "valid":
                raise _LLMFixError(
                    f"[{outcome.code}] LLM 编辑提案校验失败 "
                    f"(修复指令一次后仍失败): {outcome.message}"
                )
            data = checker.last_data
            if data is None:
                raise _LLMFixError(
                    f"[{CODE_PROPOSAL_INVALID}] 编辑提案校验通过但数据丢失 (程序错误)"
                )
            try:
                explanation, ops = _parse_edit_ops(data)
            except _LLMFixError as exc:
                raise _LLMFixError(f"[{CODE_PROPOSAL_INVALID}] 编辑提案解析失败: {exc}") from exc
            if self.semantic_cache is not None and cache_key_value:
                self.semantic_cache.put(
                    cache_key_value,
                    {"explanation": explanation, "ops": ops},
                    kind="diagnose",
                )
            # W114 anchor repair: an apply_edit/apply_patch whose old-string
            # anchor was rejected arms exactly ONE more model round-trip
            # whose instruction carries up to 3 real candidate anchor lines
            # (with line numbers) read from the target file, so the retry
            # can quote an old string that really exists. A second anchor
            # rejection fails honestly with the original message.
            anchor_retried = False
            while True:
                # W156: remember every validated proposal (canonical form);
                # an exact repeat of an earlier iteration's proposal fails
                # the step here, before execution or any further LLM call.
                # The anchor-repair retry inside this same invocation is
                # EXEMPT (W161): its second rejection stays the pinned M1
                # FAILED (被拒) semantics — never a repeat error.
                if not anchor_retried:
                    self._record_proposal(ops)
                try:
                    edited = self._execute_edit_ops(ops)
                    break
                except _AnchorRejectError as reject:
                    if anchor_retried:
                        raise _LLMFixError(reject.message) from None
                    anchor_retried = True
                    instruction = self._anchor_repair_instruction(
                        reject.path, reject.old, reject.message
                    )
                    repaired = produce(instruction)
                    outcome = checker.check(repaired)
                    if outcome.status != "valid":
                        raise _LLMFixError(
                            f"[{outcome.code}] 锚点修复重试后编辑提案仍无效: {outcome.message}"
                        ) from None
                    data = checker.last_data
                    if data is None:
                        raise _LLMFixError(
                            f"[{CODE_PROPOSAL_INVALID}] 锚点修复重试后数据丢失 (程序错误)"
                        ) from None
                    try:
                        explanation, ops = _parse_edit_ops(data)
                    except _LLMFixError as exc:
                        raise _LLMFixError(
                            f"[{CODE_PROPOSAL_INVALID}] 锚点修复重试解析失败: {exc}"
                        ) from exc
        else:
            raw_explanation = cached.get("explanation")
            explanation = raw_explanation if isinstance(raw_explanation, str) else ""
            raw_ops = cached.get("ops")
            ops = raw_ops if isinstance(raw_ops, list) else []
            self._record_proposal(ops)
            try:
                edited = self._execute_edit_ops(ops)
            except _AnchorRejectError as reject:
                # a cached proposal has no producer to repair through
                raise _LLMFixError(reject.message) from None
        if explanation:
            return f"[LLM 诊断] {explanation}", edited
        return diagnosis, edited

    def _execute_edit_ops(self, ops: list[dict[str, Any]]) -> list[str]:
        """Execute validated edit ops through the Editor (or registry).

        Every op has already passed EditProposalSelfCheck; an
        apply_edit/apply_patch anchor rejection surfaces as _AnchorRejectError
        carrying path/old/message so the caller can arm exactly one
        anchor repair; every other rejection raises _LLMFixError (M1
        semantics — never faked).
        """
        edited: list[str] = []
        for op in ops:
            action = op.get("action")
            path = op.get("path")
            new_value = op.get("new")
            if not isinstance(path, str) or not path.strip():
                raise _LLMFixError(f"编辑操作缺少合法 path: {op!r}")
            if action == "apply_edit":
                old_value = op.get("old")
                if not isinstance(old_value, str) or not isinstance(new_value, str):
                    raise _LLMFixError(f"apply_edit 需要字符串 old/new: {op!r}")
                if self.tool_registry is not None:
                    tool_result = self.tool_registry.dispatch(
                        self.tool_registry.build_tool_call(
                            "apply_patch",
                            {"path": path, "old": old_value, "new": new_value},
                        )
                    )
                    if tool_result.status != "ok":
                        raise _AnchorRejectError(
                            path,
                            old_value,
                            f"apply_patch 被拒 ({path}): {tool_result.summary}",
                        )
                else:
                    try:
                        self.editor.apply_edit(path, old_value, new_value)
                    except EditError as exc:
                        raise _AnchorRejectError(
                            path, old_value, f"apply_edit 被拒 ({path}): {exc}"
                        ) from exc
            elif action == "write_file":
                if not isinstance(new_value, str):
                    raise _LLMFixError(f"write_file 需要字符串 new: {op!r}")
                if self.tool_registry is not None:
                    tool_result = self.tool_registry.dispatch(
                        self.tool_registry.build_tool_call(
                            "create_file", {"path": path, "content": new_value}
                        )
                    )
                    if tool_result.status != "ok":
                        raise _LLMFixError(f"create_file 被拒 ({path}): {tool_result.summary}")
                else:
                    try:
                        self.editor.write_file(path, new_value)
                    except EditError as exc:
                        raise _LLMFixError(f"write_file 被拒 ({path}): {exc}") from exc
            else:
                raise _LLMFixError(f"未知编辑动作 {action!r} (仅支持 apply_edit|write_file)")
            if path not in edited:
                edited.append(path)
        return edited

    def _record_proposal(self, ops: list[dict[str, Any]]) -> None:
        """Canonicalize a validated proposal and reject an exact repeat (W156).

        Every validated proposal attempted by this loop run is remembered;
        an exact repeat (same canonical edit set, sorted by
        (action, path, old, new)) raises _ProposalRepeatError carrying the
        iteration that first attempted it — the caller fails the step with
        the stable code instead of executing the repeat or calling the
        model again. W163: in the main diagnose path the first repeat also
        arms exactly ONE diversified retry for the next diagnose call; the
        bare rejection here keeps the no-producer paths (cache hit,
        envelope mode) on the W156 semantics.
        """
        key = _canonical_proposal(ops)
        previous = self._attempted_proposals.get(key)
        if previous is not None:
            raise _ProposalRepeatError(previous)
        self._attempted_proposals[key] = self.total_iterations

    def _take_diversification(self, step: Step) -> str | None:
        """Consume the ONE armed diversified retry for this step (W163).

        The first repeated proposal arms the flag in _run_step; the next
        diagnose call consumes it here and carries the diversification
        instruction exactly once. Returns None when nothing is armed (the
        common path) or when a different step owns the armed retry.
        """
        if self._diversification_armed != step.id:
            return None
        self._diversification_armed = None
        return self._diversification_instruction()

    def _diversification_instruction(self) -> str:
        """The W163 diversified repair instruction for a repeated proposal.

        Lists up to _MAX_DIVERSIFY_SUMMARIES earlier proposals as canonical
        per-edit summaries and explicitly forbids repeating any previous
        edit — the model must propose a DIFFERENT fix path (different
        file, different edit strategy).
        """
        previous = self._previous_proposal_summaries()
        if previous:
            block = "\n".join(f"- {item}" for item in previous)
        else:
            block = "- (无记录 — 请选择与之前不同的编辑路径)"
        return (
            "EDIT PROPOSAL SELF-CHECK — your previous proposals were identical to an "
            "earlier attempt — propose a DIFFERENT fix path (different file, different "
            "edit strategy); do NOT repeat any previous edit.\n"
            f"Previous attempts (canonical per-edit summaries, up to "
            f"{_MAX_DIVERSIFY_SUMMARIES} shown, newest first):\n"
            f"{block}\n"
            "Respond with exactly ONE corrected JSON object with top-level keys "
            '"diagnosis" (string, one sentence) and "edits" (array of edit '
            "operations) — no markdown fences, no prose."
        )

    def _previous_proposal_summaries(self) -> list[str]:
        """Up to _MAX_DIVERSIFY_SUMMARIES canonical per-edit summaries of
        the proposals already attempted this run (W163), newest first."""
        ordered = sorted(
            self._attempted_proposals.items(), key=lambda pair: pair[1], reverse=True
        )
        summaries: list[str] = []
        for key, iteration in ordered[:_MAX_DIVERSIFY_SUMMARIES]:
            edits = [
                self._canonical_edit_summary(action, path, old, new)
                for action, path, old, new in key
            ]
            summaries.append(f"[迭代 {iteration}] " + "; ".join(edits))
        return summaries

    @staticmethod
    def _canonical_edit_summary(action: str, path: str, old: str, new: str) -> str:
        """One canonical per-edit summary line for the diversification
        instruction (W163): action, path and clipped old/new strings."""

        def clip(text: str) -> str:
            if len(text) <= _EDIT_SUMMARY_CLIP:
                return text
            return text[: _EDIT_SUMMARY_CLIP] + "…"

        if action == "write_file":
            return f"write_file {path}: new={clip(new)!r}"
        return f"apply_edit {path}: old={clip(old)!r} new={clip(new)!r}"

    def _anchor_candidates(self, path: str, old: str) -> list[tuple[int, str]]:
        """Up to 3 real candidate anchor lines (numbered) from the target file.

        Prefers lines containing the longest identifier token of the
        rejected old string; falls back to the first non-blank lines.
        """
        try:
            lines = self.editor.read_file(path)
        except EditError:
            return []
        tokens = re.findall(r"[A-Za-z0-9_]{3,}", old)
        probe = max(tokens, key=len) if tokens else ""
        hits = [(number, text) for number, text in lines if probe and probe in text]
        if not hits:
            hits = [(number, text) for number, text in lines if text.strip()]
        return hits[:_MAX_ANCHOR_CANDIDATES]

    def _anchor_repair_instruction(self, path: str, old: str, rejection: str) -> str:
        """ONE deterministic repair instruction for an anchor rejection (W114).

        Carries up to 3 REAL candidate anchor lines with line numbers from
        the target file so the retry can quote an old string that exists.
        """
        candidates = self._anchor_candidates(path, old)
        if candidates:
            block = "\n".join(f"line {number}: {text}" for number, text in candidates)
        else:
            block = "(目标文件不可读或无内容 — 请改用 write_file)"
        return (
            "EDIT PROPOSAL SELF-CHECK — your apply_edit was REJECTED and NOT executed.\n"
            f"error: {rejection}\n"
            f"Real anchor candidates from the CURRENT content of {path} (numbered) — "
            "copy ONE of these lines EXACTLY (byte-for-byte, indentation and inline "
            'whitespace included) as the "old" string of your corrected apply_edit '
            f"(up to {_MAX_ANCHOR_CANDIDATES} candidates shown):\n"
            f"{block}\n"
            "Respond with exactly ONE corrected JSON object with top-level keys "
            '"diagnosis" (string, one sentence) and "edits" (array of edit '
            "operations) — no markdown fences, no prose."
        )

    def _diagnose_call(
        self,
        client: LLMClient,
        messages: list[LLMMessage],
        step: Step,
        prompt_text: str,
        route: ProviderRoute | None,
    ) -> LLMResponse:
        """One diagnose chat round-trip; a cheap-tier failure falls back to
        exactly one strong retry, counted by the router (on_failure)."""

        def once() -> LLMResponse:
            response = client.chat_sync(
                messages,
                label=f"diagnose:{step.id}",
                kind="diagnose",
                job_id=self.job_id,
                step_id=step.id,
                thinking=resolve_craft_thinking("diagnose"),
                response_format={"type": "json_object"},
                estimated_prompt_tokens=max(1, len(prompt_text) // 4),
            )
            self.llm_calls += 1
            return response

        if route is None or route.tier != "cheap" or self.router is None:
            return once()
        try:
            return once()
        except LLMUnavailableError:
            self.router.on_failure(route)
            return once()

    def _llm_fix_envelope(
        self,
        client: LLMClient,
        base: str,
        context: dict[str, str],
        step: Step,
        diagnosis: str,
    ) -> tuple[str, list[str]]:
        """W44 self-checked envelope path: the model must answer with one
        JSON Action Envelope, validated through ToolCallSelfCheck
        .check_with_retry with the model round-trip injected as the
        producer callable. One retry is armed on an invalid envelope; a
        second invalid envelope gives up with the stable registry error
        code and the step fails with honest M1 semantics."""
        checker = self.tool_call_self_check
        registry = self.tool_registry
        if checker is None or registry is None:
            # Constructor validation makes this unreachable; kept for types.
            raise _LLMFixError("信封自检路径缺少 checker/registry (构造期应已拦截)")
        route = self.router.route("diagnose") if self.router is not None else None
        produced: list[object] = []

        def produce(instruction: str | None) -> object:
            sections = dict(context)
            if instruction:
                sections["self_check_repair"] = instruction
            built = assemble(base, "diagnose", sections, include_envelope=True)
            response = self._diagnose_call(
                client,
                [LLMMessage(role="user", content=built.text)],
                step,
                built.text,
                route,
            )
            try:
                payload = extract_json_object(response.content or "")
            except (json.JSONDecodeError, TypeError, ValueError):
                # The checker reports "not a JSON object" and arms its retry.
                payload = response.content
            produced.append(payload)
            return payload

        outcome = checker.check_with_retry(produce)
        if outcome.status != "valid":
            raise _LLMFixError(
                f"工具调用信封自检未通过 ({outcome.status}, code={outcome.code}): {outcome.message}"
            )
        envelope = produced[-1]
        if not isinstance(envelope, dict):
            raise _LLMFixError("信封自检通过但载荷不是 JSON 对象 (内部不一致)")
        action = envelope.get("action")
        params = envelope.get("params")
        raw_version = envelope.get("version")
        if not isinstance(action, str) or not isinstance(params, dict):
            raise _LLMFixError("信封自检通过但 action/params 类型非法 (内部不一致)")
        if action not in ("apply_patch", "create_file"):
            raise _LLMFixError(
                f"信封自检通过但工具 {action!r} 不是编辑工具 (仅支持 apply_patch|create_file)"
            )
        version = (
            raw_version
            if isinstance(raw_version, int) and not isinstance(raw_version, bool)
            else None
        )
        tool_result = registry.dispatch(registry.build_tool_call(action, params, version=version))
        if tool_result.status != "ok":
            raise _LLMFixError(f"{action} 被拒: {tool_result.summary}")
        path = params.get("path")
        if not isinstance(path, str) or not path.strip():
            raise _LLMFixError("信封缺少合法 path")
        # W156: canonicalize the validated envelope into the shared edit-op
        # shape so an exact repeat of this proposal is caught next time.
        if action == "apply_patch":
            envelope_ops: list[dict[str, Any]] = [
                {
                    "action": "apply_edit",
                    "path": path,
                    "old": params.get("old"),
                    "new": params.get("new"),
                }
            ]
        else:
            envelope_ops = [
                {"action": "write_file", "path": path, "new": params.get("content")}
            ]
        self._record_proposal(envelope_ops)
        return diagnosis, [path]

    def _diagnose_context(
        self,
        step: Step,
        result: ExecResult | None,
        diagnosis: str,
        *,
        envelope_mode: bool = False,
    ) -> dict[str, str]:
        """Failure context for the diagnose prompt: step schema, deterministic
        diagnosis, failure output tail, the current real content of each
        candidate source file as the edit anchor (up to 2000 lines, capped),
        the editor API contract and the JSON output contract. envelope_mode
        (W44 self-check) swaps the edit-proposal schema for the JSON Action
        Envelope contract."""
        # W113/W114 anchor fix: the prompt must carry the CURRENT real
        # content of every candidate SOURCE file (bounded to the first
        # MAX_READ_LINES lines — 2000 since W114, previously 400 — raw
        # lines, no numbering) so the model quotes old strings from the
        # real text instead of reconstructing code from memory
        # (pallets__flask-4045: apply_edit 拒绝 old 未命中 src/flask/helpers.py).
        # Test files are excluded — editing them is forbidden and the hidden
        # tests are applied by the harness after craft.
        snippets: list[str] = []
        excluded_test_targets: list[str] = []
        # W143: mentioned paths resolve through the shared suffix resolver,
        # so the anchor ships the real file content even when the plan
        # carries a repo-relative suffix (flask-4045: 'flask/blueprints.py'
        # -> 'src/flask/blueprints.py'); unresolvable paths keep the honest
        # <不可读> marker with the candidates found.
        anchor_files = self._workspace_py_files()
        for target in step.target_files[:8]:
            if is_test_file_path(target):
                excluded_test_targets.append(target)
                continue
            resolved, suffix_candidates = _resolve_mentioned_path(target, anchor_files)
            if resolved is None:
                try:
                    lines = self.editor.read_file(target, limit=MAX_READ_LINES)
                except EditError:
                    detail = ""
                    if suffix_candidates:
                        detail = f"; 后缀匹配不唯一: {sorted(suffix_candidates)}"
                    snippets.append(f"--- {target} ---\n<不可读>{detail}")
                    continue
                resolved = target
            else:
                try:
                    lines = self.editor.read_file(resolved, limit=MAX_READ_LINES)
                except EditError:
                    snippets.append(f"--- {resolved} ---\n<不可读>")
                    continue
            over_line_limit = len(lines) >= MAX_READ_LINES and bool(
                self.editor.read_file(resolved, offset=MAX_READ_LINES + 1, limit=1)
            )
            shown = lines[:MAX_READ_LINES]
            text = "\n".join(line for _, line in shown)
            if len(text) > _ANCHOR_CHAR_CAP:
                cut = text.rfind("\n", 0, _ANCHOR_CHAR_CAP)
                if cut < 0:
                    cut = _ANCHOR_CHAR_CAP
                text = text[:cut] + "\n... (截断)"
            elif over_line_limit:
                text += f"\n... (仅显示前 {MAX_READ_LINES} 行)"
            snippets.append(f"--- {resolved} ---\n{text}")
        anchor_header = (
            "FILE CONTENT ANCHOR — quote old strings EXACTLY from the file content "
            "above: each candidate SOURCE file's current real text follows (at most "
            f'the first {MAX_READ_LINES} lines); every apply_edit "old" must be '
            "copied byte-for-byte from a real line above (indentation and inline "
            "whitespace included). Never reconstruct code from memory. Test files "
            "are excluded — hidden tests are applied by the harness itself after "
            "craft."
        )
        if excluded_test_targets:
            anchor_header += f" Excluded test files: {sorted(excluded_test_targets)}."
        target_section = (
            f"{anchor_header}\n\n" + "\n\n".join(snippets)
            if snippets
            else f"{anchor_header}\n\n(无候选源文件)"
        )
        if self.tool_registry is not None:
            tool_surface = wrap_data_section(self.tool_registry.envelope_block())
        else:
            tool_surface = _EDITOR_API_BLOCK
        return {
            "step": json.dumps(step.to_dict(), ensure_ascii=False, indent=2),
            "failure_diagnosis": diagnosis,
            "failure_output": (result.output_tail if result is not None else "") or "(无)",
            "forbidden_changes": "\n".join(self.spec.forbidden_changes) or "(无)",
            "target_files": target_section,
            "task_memory": self.memory.summarize_for_prompt() or "(无任务记忆)",
            "editor_api": tool_surface,
            "output_schema": (JSON_ACTION_ENVELOPE_BLOCK if envelope_mode else _EDIT_OPS_SCHEMA),
        }

    @staticmethod
    def _error_signature(step: Step, result: ExecResult | None, note: str = "") -> str:
        if result is None:
            # 首跑缺口修复 (pallets__flask-4992): grep/read-only criteria run
            # no command at all, so there is no exec output to quote — the
            # real failure reason rides the note instead of a misleading
            # "<no-exec-output>" placeholder.
            core = note.strip()[:160] if note.strip() else "<no-exec-output>"
            return f"{step.id}|{core}"
        match = _ASSERT_EQ_RE.search(result.output_tail)
        core = match.group(0).strip() if match else result.output_tail[-160:].strip()
        return f"{step.id}|{core}"

    # -- artifacts ----------------------------------------------------------

    @staticmethod
    def _result_dict(result: ExecResult | None, note: str = "") -> dict[str, Any]:
        if result is None:
            return {"exit_code": -1, "failed_tests": [], "log_tail": note[:1000]}
        return {
            "exit_code": result.exit_code,
            "failed_tests": extract_pytest_failed_tests(f"{result.stdout}\n{result.stderr}"),
            "log_tail": result.output_tail[-1000:],
        }

    def _checkpoint(
        self,
        *,
        step_id: str,
        iteration: int,
        diagnosis: str,
        edits_applied: list[str],
        build_result: dict[str, Any],
        verdict: str,
    ) -> None:
        entry = {
            "job_id": self.job_id,
            "step_id": step_id,
            "iteration": iteration,
            "diagnosis": diagnosis,
            "edits_applied": list(edits_applied),
            "build_result": build_result,
            "verdict": verdict,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.checkpoint_entries.append(entry)
        payload = {
            "job_id": self.job_id,
            "workspace": str(self.workspace),
            "task_key": self.task_key,
            "last_green_step": self.last_green_step,
            "entries": self.checkpoint_entries,
        }
        try:
            write_json_atomic(self.artifact_dir / "checkpoint.json", payload)
            self._record_file_writes_from_audit(step_id)
            self.memory.add(
                "budget",
                f"tokens={round(self.client.budget.used if self.client else 0.0, 1)} "
                f"iterations={self.total_iterations} tool_calls={self.tool_calls_used}",
                step_id=step_id,
            )
            self.memory.save(self.artifact_dir)
        except CraftPlanError as exc:
            raise CraftLoopError(f"checkpoint 写入失败: {exc}") from exc
        except MemoryError as exc:
            raise CraftLoopError(f"memory 写入失败: {exc}") from exc
        self._store_set_progress(step_id, iteration)

    def _record_file_writes_from_audit(self, step_id: str) -> None:
        """file_written facts come from the editor audit (卷 XXI §21.1):
        write/edit/move/delete actions — the authoritative trail, not the
        fix functions' return values."""
        for entry in self.editor.audit:
            if entry.action in ("write", "edit"):
                self.memory.add("file_written", entry.path, step_id=step_id)
            elif entry.action == "delete":
                self.memory.add("file_written", f"deleted: {entry.path}", step_id=step_id)
            elif entry.action == "move":
                destination = entry.detail.removeprefix("→ ").strip()
                self.memory.add("file_written", f"{entry.path} -> {destination}", step_id=step_id)

    def interrupt_checkpoint(self) -> None:
        """Ctrl-C flush (卷 XXI §21.3): persist the in-flight step as an
        'interrupted' checkpoint entry plus memory.json, so craft resume
        continues after the last green step. Never writes report.json —
        that is a terminal artifact."""
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        step_id = (
            self._current_step.id
            if self._current_step is not None
            else (self.last_green_step or "")
        )
        entry = {
            "job_id": self.job_id,
            "step_id": step_id,
            "iteration": 0,
            "diagnosis": "用户中断 (Ctrl-C), 当前步骤未完成",
            "edits_applied": [],
            "build_result": {"exit_code": -1, "failed_tests": [], "log_tail": ""},
            "verdict": "interrupted",
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        self.checkpoint_entries.append(entry)
        payload = {
            "job_id": self.job_id,
            "workspace": str(self.workspace),
            "task_key": self.task_key,
            "last_green_step": self.last_green_step,
            "entries": self.checkpoint_entries,
        }
        try:
            write_json_atomic(self.artifact_dir / "checkpoint.json", payload)
            self.memory.save(self.artifact_dir)
        except CraftPlanError as exc:
            raise CraftLoopError(f"中断落盘失败 (checkpoint): {exc}") from exc
        except MemoryError as exc:
            raise CraftLoopError(f"中断落盘失败 (memory): {exc}") from exc

    def _finish(self, result: str) -> dict[str, Any]:
        changed_files = sorted(
            {
                entry.path
                for entry in self.editor.audit
                if entry.action in ("write", "edit", "move", "delete")
            }
        )
        # Base snapshots for the Java contract checkers: the first Editor
        # backup per path is the original pre-craft content (audit order:
        # backup entry precedes its write/edit entry).
        base_files: dict[str, str] = {}
        for entry in self.editor.audit:
            if entry.action != "backup" or entry.path in base_files:
                continue
            backup_name = entry.detail.removeprefix("→ ").strip()
            backup_path = self.artifact_dir / "backup" / backup_name
            try:
                base_files[entry.path] = backup_path.read_text(encoding="utf-8")
            except OSError:
                continue
        if self.skip_self_verify:
            self_verify_report: dict[str, Any] = {
                "status": "skipped",
                "findings": [],
                "note": "--no-self-verify: 自校验被显式跳过 (report 诚实标注 skipped)",
            }
        else:
            try:
                self_verify_report = self_verify(
                    changed_files, self.workspace, base_files=base_files
                )
            except Exception as exc:
                # The gate must never lose the report: honest degradation.
                self_verify_report = {
                    "status": "skipped",
                    "findings": [],
                    "note": f"自校验执行异常, 诚实降级为 skipped: {exc!r}",
                }
        if self_verify_report["status"] == "failed":
            if result == "DONE":
                result = "FAILED"
                self_verify_report["note"] = (
                    str(self_verify_report.get("note"))
                    + "; 自校验硬门未通过: 终态 DONE 覆盖为 FAILED "
                    "(编辑不回滚, 现场保留供人工处置)"
                )
            else:
                self_verify_report["note"] = (
                    str(self_verify_report.get("note"))
                    + f"; 自校验硬门未通过, 但任务终态原为 {result} (非 DONE), 不改变终态"
                )
        # W35 gate composition: whenever the M3 self-verify gate actually ran,
        # run the full five-gate pipeline too and embed its summary. This is
        # informational here — the loop does NOT block on it beyond the
        # existing self-verify hard gate; craft/accept.py owns the full
        # closure (gates + SpecProof verification + certificate).
        gates_report: dict[str, Any] | None = None
        if not self.skip_self_verify:
            gates_report = self._run_gate_pipeline(changed_files, base_files, self_verify_report)
        self.memory.add(
            "decision",
            f"自校验: {self_verify_report['status']} "
            f"(findings={len(self_verify_report.get('findings') or [])})",
        )
        elapsed = self.now_fn() - self.started_at
        tokens_used = self.client.budget.used if self.client is not None else 0.0
        report: dict[str, Any] = {
            "job_id": self.job_id,
            "mode": self.plan.mode,
            "result": result,
            "steps": [state.to_dict() for state in self.states],
            "diff_stat": {"files_changed": len(changed_files), "files": changed_files},
            "self_verify": self_verify_report,
            "budget_used": {
                "tokens": round(tokens_used, 1),
                "iterations": self.total_iterations,
                "seconds": round(elapsed, 1),
            },
            "audit_trail": [entry.to_dict() for entry in self.editor.audit],
        }
        if gates_report is not None:
            report["gates"] = gates_report
        if self.client is not None:
            report["llm_usage"] = self.client.stats_report()
            # W163 transient-timeout retry audit: a stable int counter next
            # to llm_usage (duck-typed clients default to 0). Only present
            # when a client exists, so deterministic reports keep their
            # exact key set.
            report["llm_timeout_retries"] = int(
                getattr(self.client, "timeout_retries", 0)
            )
        if self.tool_registry is not None:
            report["tool_registry"] = {
                "present": True,
                "tools": self.tool_registry.tool_names(),
                "dispatches": self.tool_registry.dispatch_count,
            }
        # W44 gains: tool-call self-check counters (success rate included),
        # router fallbacks, cache hits and the judge-persona flag. Zeros
        # when nothing is configured — the report shape is stable.
        self_check_metrics: dict[str, Any] = (
            self.tool_call_self_check.metrics() if self.tool_call_self_check is not None else {}
        )
        report["gains"] = {
            "tool_call_attempts": int(self_check_metrics.get("attempts") or 0),
            "tool_call_valid": int(self_check_metrics.get("valid") or 0),
            "tool_call_retried": int(self_check_metrics.get("retried") or 0),
            "tool_call_success_rate": float(
                self_check_metrics.get("tool_call_success_rate") or 0.0
            ),
            "router_fallback_count": (
                int(self.router.fallback_count) if self.router is not None else 0
            ),
            "cache_hits": (int(self.semantic_cache.hits) if self.semantic_cache is not None else 0),
            "judge_persona_applied": int(self._judge_persona_applied),
        }
        if self.plan.llm_fallback_reason:
            report["llm_fallback_reason"] = self.plan.llm_fallback_reason
        self.memory.add("decision", f"任务终态: {result} (迭代 {self.total_iterations})")
        self.memory.add(
            "budget",
            f"tokens={round(tokens_used, 1)} iterations={self.total_iterations} "
            f"tool_calls={self.tool_calls_used} seconds={round(elapsed, 1)}",
        )
        try:
            write_json_atomic(self.artifact_dir / "report.json", report)
            self.memory.save(self.artifact_dir)
        except CraftPlanError as exc:
            raise CraftLoopError(f"report 写入失败: {exc}") from exc
        except MemoryError as exc:
            raise CraftLoopError(f"memory 写入失败: {exc}") from exc
        # W35 terminal write: entering a terminal status releases the lease
        # automatically; a supervisor cancel that raced us wins (its
        # projection is final and is never overwritten).
        if self.store is not None:
            if result == "CANCELLED":
                report["job_store_note"] = (
                    "作业已被 supervisor 取消 (cancel 优先于租约), 不写终态投影"
                )
            else:
                mapped: JobStatus = "succeeded" if result == "DONE" else "failed"
                try:
                    self.store.update_status(self.job_id, mapped, result_json=report)
                except InvalidJobTransitionError:
                    report["job_store_note"] = (
                        "终态投影被 supervisor 覆盖 (cancel 优先), result_json 未更新"
                    )
        return report

    def _run_gate_pipeline(
        self,
        changed_files: list[str],
        base_files: dict[str, str],
        self_verify_report: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the five-gate pipeline at finish; gate 5 reuses the M3 report
        computed above (never re-scans), and any pipeline crash degrades to
        an honest error summary instead of losing the report."""

        def passthrough(
            changed: list[str],
            workspace: Path,
            base_files: Mapping[str, str] | None = None,
        ) -> dict[str, Any]:
            return self_verify_report

        try:
            pipeline = GatePipeline(
                self.workspace, executor=self.executor, self_verify_fn=passthrough
            )
            bundle = ChangeBundle(task_id=self.job_id, changed_files=list(changed_files))
            return pipeline.run(bundle, base_files=base_files).to_dict()
        except Exception as exc:
            return {
                "task_id": self.job_id,
                "overall": "error",
                "overall_note": f"门禁组合执行异常, 诚实降级 (不伪造结果): {exc!r}",
                "duration_ms": 0,
                "gates": [],
                "summary": (
                    f"GATES: task={self.job_id} overall=error duration_ms=0 (组合执行异常: {exc!r})"
                ),
            }

    @classmethod
    def from_checkpoint(
        cls,
        artifact_dir: str | Path,
        *,
        fix_registry: dict[str, FixFunction] | None = None,
        budget: Budget | None = None,
        exec_mode: str | None = None,
        exec_timeout: int = 600,
        python: str | None = None,
        client: LLMClient | None = None,
        tool_registry: ToolRegistry | None = None,
        tool_call_self_check: ToolCallSelfCheck | None = None,
        router: ModelRouter | None = None,
        semantic_cache: SemanticCache | None = None,
        judge_persona: bool = False,
        store: AgentJobStore | None = None,
        lease_ttl_seconds: float = 900,
    ) -> CraftLoop:
        """In-memory resume interface: rebuild the loop from .specraft
        artifacts and continue after the last green step (M1: no MySQL)."""
        directory = Path(artifact_dir)
        try:
            plan_data = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
            checkpoint_data = json.loads(
                (directory / "checkpoint.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise CraftLoopError(f"无法读取作业产物 ({directory}): {exc}") from exc
        plan = Plan.from_dict(plan_data)
        if not isinstance(checkpoint_data, dict):
            raise CraftLoopError("checkpoint.json 顶层必须是对象")
        job_id = checkpoint_data.get("job_id")
        workspace_raw = checkpoint_data.get("workspace")
        task_key = checkpoint_data.get("task_key")
        if not isinstance(job_id, str) or not isinstance(workspace_raw, str):
            raise CraftLoopError("checkpoint.json 缺少 job_id/workspace 字段")
        if not isinstance(task_key, str):
            task_key = None
        entries_raw = checkpoint_data.get("entries", [])
        if not isinstance(entries_raw, list):
            raise CraftLoopError("checkpoint.json 的 entries 应为数组")
        entries = [entry for entry in entries_raw if isinstance(entry, dict)]
        last_green = checkpoint_data.get("last_green_step") or ""
        states = [StepState(step=step) for step in plan.steps]
        green_index = -1
        for index, step in enumerate(plan.steps):
            if step.id == last_green:
                green_index = index
        for index in range(green_index + 1):
            states[index].status = "green"
            states[index].evidence = {
                "resumed": True,
                "note": "从 checkpoint 恢复: 该步骤上一轮已绿, 不重跑",
            }
        total_iterations = sum(int(entry.get("iteration", 0)) for entry in entries)
        try:
            memory = TaskMemory.load(directory)
        except MemoryError as exc:
            raise CraftLoopError(f"memory.json 损坏, 无法恢复 ({directory}): {exc}") from exc
        spec = TaskSpec(title=plan.task_title, description="")
        loop = cls(
            spec,
            plan,
            Path(workspace_raw),
            budget=budget,
            job_id=job_id,
            artifact_dir=directory,
            fix_registry=fix_registry,
            exec_mode=exec_mode,
            exec_timeout=exec_timeout,
            python=python,
            states=states,
            checkpoint_entries=entries,
            total_iterations=total_iterations,
            task_key=task_key,
            client=client,
            memory=memory,
            tool_registry=tool_registry,
            tool_call_self_check=tool_call_self_check,
            router=router,
            semantic_cache=semantic_cache,
            judge_persona=judge_persona,
            store=store,
            lease_ttl_seconds=lease_ttl_seconds,
        )
        loop.last_green_step = str(last_green)
        return loop
