"""#109 — one field name, fifteen scales: the `verdict` channels, gated both ways.

DRILLS recorded this as the last open vocabulary item: `verdict` is reused by a
job's outcome, a matrix row's `result`, an evaluation case, a Craft checkpoint
and a benchmark classification, so no answer existed to "which scale does this
word belong to". The channels are declared in `evidence/verdict_channels.py`;
this gate re-derives every literal from source instead of trusting the
declaration, and asserts:

* every literal written in product code is claimed by exactly one channel's
  owners (a new word in an unowned file fails here, by name and line);
* every declared word is written by its owners — or carries a witness line that
  really contains it, so "declared but dead" cannot pass;
* a non-literal write (`verdict = some_call()`, `"verdict": verdict`) is owned
  too: a file may not say a word the scanner cannot read without saying so;
* channels whose authority lives elsewhere (a `Literal`, a pydantic `pattern`,
  the state machine) agree with that authority, not with a copy;
* the Web glosses for the channels a human reads (evaluation, 验证结论) have
  exactly the words the product writes: no raw English for a value that is
  produced, and no translation for a value nothing produces.

Scan shapes (all six, because #90's false measurement came from scanning only
dict keys): dict-key, keyword argument, keyword collection, assignment,
attribute compare, variable compare — plus `.get("verdict", default)` and a
separate record for non-literal writes, which are owned but not enumerable.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

from evidence.verdict_channels import CHANNELS, VerdictChannel

REPO = Path(__file__).resolve().parents[2]

# Every top-level directory that can hold product Python. `tests` is excluded on
# purpose: a fixture writing a value nobody produces is the #90/#87 failure mode
# (a dead word kept alive by a green test), not a producer.
SCAN_ROOTS = (
    "agent", "api", "cli", "craft", "evidence", "experiments", "integrations",
    "mcp", "ops", "providers", "sandbox", "scripts", "storage",
)
# Not product code, each with the reason it is not a producer of this field.
EXEMPT: dict[str, str] = {
    "scripts/bench_gen_tasks_data.py":
        "third-party dataset fixture: `green`/`progress` are the upstream task "
        "data this generator mirrors, written into generated JSON, never read "
        "back as a product verdict",
    "scripts/test_c6_junit_diff.py":
        "self-contained demo script: its report strings are prose "
        "(\"REGRESSION DETECTED\", \"COMPLIANT (both pass)\") for a human reading "
        "one run, not a value any consumer parses",
}
SKIP_DIR_PARTS = {".venv", ".venv312", "node_modules", ".git", "__pycache__"}


@dataclass(frozen=True)
class Hit:
    path: str  # repo-relative, posix
    line: int
    shape: str
    value: str | None  # None = a non-literal write: owned, not enumerable

    def __str__(self) -> str:
        return f"{self.path}:{self.line} [{self.shape}] {self.value!r}"


@dataclass
class Scan:
    hits: list[Hit] = field(default_factory=list)

    @property
    def valued(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for hit in self.hits:
            if hit.value is not None:
                out.setdefault(hit.value, set()).add(hit.path)
        return out

    @property
    def files(self) -> set[str]:
        return {hit.path for hit in self.hits}

    @property
    def opaque_files(self) -> set[str]:
        return {hit.path for hit in self.hits if hit.value is None}


def _literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


#: A `.get` default of `""`, or a dict value of `None`, writes "no word at all".
#: Neither is a member of any scale, so neither is recorded as one.
ABSENT = ("", None)


def _string_branches(node: ast.AST) -> set[str]:
    """Every string literal a conditional/ternary value can take.

    `verdict = "A" if x else "B" if y else "C"` is a producer of three words,
    none of which is a plain `ast.Constant`; without this the scanner would
    report a channel whose words are "declared but never written".
    """
    found: set[str] = set()
    for sub in ast.walk(node):
        value = _literal(sub)
        if value is not None and value not in ABSENT:
            found.add(value)
    return found


def scan_source(text: str, path: str) -> list[Hit]:
    """Writes, literal comparisons, and non-literal writes (recorded as opaque).

    `value is None` means "this file writes a verdict the scanner cannot
    enumerate" — still an owned write, so the ownership rule applies.
    """
    hits: list[Hit] = []

    def write(line: int, shape: str, node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and node.value not in ABSENT:
                hits.append(Hit(path, line, shape, node.value))
            return  # None / "" write no word at all
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            for elt in node.elts:
                if (
                    isinstance(elt, ast.Constant)
                    and isinstance(elt.value, str)
                    and elt.value not in ABSENT
                ):
                    hits.append(Hit(path, line, f"{shape}-collection", elt.value))
            return
        # A conditional (`"A" if x else "B"`, `f"PASS — {why}"`) is a runtime
        # decision: what gets written depends on data this gate does not have,
        # so it is recorded as an opaque write, never as two fixed words.
        hits.append(Hit(path, line, shape, None))

    try:
        tree = ast.parse(text)
    except SyntaxError:
        return hits

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "verdict":
                    write(key.lineno, "dict-key", val)
        elif isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "verdict":
                    write(kw.lineno, "kwarg", kw.value)
            # `.get("verdict", "<default>")` — the default is what gets written
            # when the key is absent, so it is a producer, not just a read.
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and node.args
                and _literal(node.args[0]) == "verdict"
            ):
                default = node.args[1] if len(node.args) > 1 else next(
                    (k.value for k in node.keywords if k.arg == "default"), None
                )
                if default is not None:
                    write(node.lineno, "get-default", default)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {"verdict", "VERDICT"}:
                    write(node.lineno, "assign", value)
                elif (
                    isinstance(target, ast.Subscript)
                    and _literal(target.slice) == "verdict"
                ):
                    write(node.lineno, "subscript-write", value)
        elif isinstance(node, ast.Compare):
            # A comparison against a variable names no word; only a literal can
            # be checked against a declared scale, so only literals are recorded.
            operands = [node.left, *node.comparators]
            # strict=False: operands and operands[1:] differ by one by design.
            for left, right in zip(operands, operands[1:], strict=False):
                for a, b in ((left, right), (right, left)):
                    named = (
                        (isinstance(a, ast.Attribute) and a.attr == "verdict")
                        or (isinstance(a, ast.Name) and a.id in {"verdict", "VERDICT"})
                    )
                    lit = _literal(b)
                    if named and lit is not None and lit not in ABSENT:
                        hits.append(Hit(path, node.lineno, "compare", lit))
    return hits


def scan_file(path: Path) -> list[Hit]:
    rel = path.relative_to(REPO).as_posix()
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    return scan_source(text, rel)


def scan_repo() -> Scan:
    hits: list[Hit] = []
    for root_name in SCAN_ROOTS:
        root = REPO / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if SKIP_DIR_PARTS & set(path.parts):
                continue
            hits.extend(scan_file(path))
    return Scan(hits)


def _channel_for(path: str) -> VerdictChannel | None:
    matches = [c for c in CHANNELS.values() if path in c.owners]
    if len(matches) > 1:
        owners = ", ".join(sorted(c.key for c in matches))
        raise AssertionError(f"{path} is owned by more than one channel: {owners}")
    return matches[0] if matches else None


def _resolve_source(spec: str) -> frozenset[str]:
    """Read an authoritative declaration rather than trusting a copy here."""
    if spec == "api.routes.feedback::pattern":
        text = (REPO / "api/routes/feedback.py").read_text(encoding="utf-8")
        match = re.search(r'verdict:\s*str\s*=\s*Field\(pattern="\^\(([^)]*)\)\$"\)', text)
        assert match, "feedback verdict pattern not found in api/routes/feedback.py"
        return frozenset(part.strip() for part in match.group(1).split("|"))
    module_name, _, attr = spec.partition("::")
    module = __import__(module_name, fromlist=["_"])
    declared = getattr(module, attr)
    if str(getattr(declared, "__module__", "")).startswith("typing"):
        return frozenset(str(v) for v in get_args(declared))
    if isinstance(declared, dict):
        return frozenset(str(k) for k in declared)
    return frozenset(str(v) for v in declared)


def _web_text(*relpaths: str) -> str:
    return "\n".join(
        (REPO / rel).read_text(encoding="utf-8") for rel in relpaths
    )


def _ts_record_keys(text: str, name: str) -> frozenset[str]:
    """Keys of a `const NAME: Record<string, string> = { ... }` literal."""
    start = text.index(name)
    body = text[start:text.index("}", start) + 1]
    return frozenset(m or n for m, n in re.findall(r'^\s{2}(?:"([^"]+)"|(\w+)):', body, re.M))


def _ts_equality_tokens(text: str, fn: str) -> frozenset[str]:
    """`v === "X"` comparisons inside one exported function."""
    start = text.index(fn)
    body = text[start:text.index("\n}", start)]
    return frozenset(re.findall(r'=== "([^"]+)"', body))


# ─── gates ──────────────────────────────────────────────────────────────────


def test_every_product_verdict_literal_is_claimed_by_a_channel() -> None:
    scan = scan_repo()
    unowned = [
        str(hit) for hit in scan.hits
        if hit.path not in EXEMPT and _channel_for(hit.path) is None
    ]
    assert not unowned, (
        "verdict literal written by a file no channel declares — declare the "
        "channel in evidence/verdict_channels.py or exempt it with a reason:\n  "
        + "\n  ".join(sorted(unowned))
    )
    declared = {path for c in CHANNELS.values() for path in c.owners}
    empty = sorted(path for path in declared if path not in scan.files)
    assert not empty, (
        "declared owners write no verdict literal at all — either the "
        "declaration is wrong or the channel already migrated away:\n  "
        + "\n  ".join(empty)
    )


def test_a_declared_word_is_written_and_a_written_word_is_declared() -> None:
    scan = scan_repo()
    failures: list[str] = []
    for channel in CHANNELS.values():
        if not channel.owners:
            continue
        observed = {
            value for value, paths in scan.valued.items() if paths & set(channel.owners)
        }
        witnesses = channel.witnesses or {}
        witnessed = set(witnesses)
        for value, pointer in witnesses.items():
            rel, _, line = pointer.partition(":")
            path = REPO / rel
            if not path.is_file():
                failures.append(f"{channel.key}: witness file missing {pointer}")
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            if not line.isdigit() or int(line) > len(lines):
                failures.append(f"{channel.key}: witness line out of range {pointer}")
                continue
            if value not in lines[int(line) - 1]:
                failures.append(
                    f"{channel.key}: witness {pointer} does not contain {value!r} "
                    "— a witness must point at the line that writes the word"
                )
        declared = set(channel.scale)
        extra = sorted(declared - observed - witnessed)
        missing = sorted(observed - declared)
        if extra:
            failures.append(
                f"{channel.key}: declared but never written: {', '.join(extra)}"
            )
        if missing:
            failures.append(
                f"{channel.key}: written but never declared: {', '.join(missing)}"
            )
        opaque = {hit.path for hit in scan.hits if hit.value is None}
        illegal = sorted((set(channel.owners) & opaque) - set(channel.opaque))
        if illegal:
            failures.append(
                f"{channel.key}: non-literal verdict write in a file that did not "
                f"declare it opaque: {', '.join(illegal)}"
            )
    assert not failures, "\n".join(failures)


def test_opaque_writes_stay_inside_a_channel_that_declared_them() -> None:
    scan = scan_repo()
    illegal: list[str] = []
    for hit in scan.hits:
        if hit.value is not None or hit.path in EXEMPT:
            continue
        channel = _channel_for(hit.path)
        if channel is None or hit.path not in channel.opaque:
            illegal.append(str(hit))
    assert not illegal, (
        "a non-literal write to `verdict` is not enumerable, so its channel must "
        "declare the file opaque:\n  " + "\n  ".join(sorted(illegal))
    )


def test_channels_with_an_authority_agree_with_it() -> None:
    failures: list[str] = []
    for channel in CHANNELS.values():
        if not channel.source:
            continue
        authority = _resolve_source(channel.source)
        if authority != set(channel.scale):
            failures.append(
                f"{channel.key}: registry {sorted(channel.scale)} != "
                f"{channel.source} {sorted(authority)}"
            )
    assert not failures, "\n".join(failures)


def test_the_evaluation_gloss_is_exactly_the_words_the_cli_writes() -> None:
    declared = set(CHANNELS["eval_case"].scale)
    gloss = _ts_record_keys(_web_text("apps/web/src/ui/toneMap.ts"), "EVAL_VERDICT_CN")
    assert gloss == declared, (
        f"EVAL_VERDICT_CN {sorted(gloss)} != eval_case {sorted(declared)}; "
        "a produced value must be explained and an unproduced one must not be"
    )


def test_the_headline_gloss_is_exactly_the_words_the_worker_writes() -> None:
    declared = set(CHANNELS["job_summary"].scale)
    util = _web_text("apps/web/src/ui/util.tsx")
    labels = _ts_record_keys(util, "VERDICT_LABELS")
    assert labels == declared, (
        f"VERDICT_LABELS {sorted(labels)} != job_summary {sorted(declared)}; "
        "a value with no producer is a dead gloss, and this field is written by "
        "the worker in exactly three words — status words (STALE/ERROR/"
        "CANCELLED) and the matrix's UNVERIFIED belong to other channels"
    )
    toned = _ts_equality_tokens(util, "export function verdictTone")
    assert toned <= labels, (
        f"verdictTone maps {sorted(toned - labels)} which VERDICT_LABELS does not "
        "translate — a tone without a label is half a gloss"
    )


def test_the_worker_can_only_choose_words_this_channel_declares() -> None:
    """`evidence/verdict.py` names the three words without ever saying verdict."""
    tree = ast.parse((REPO / "evidence/verdict.py").read_text(encoding="utf-8"))
    chosen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", "") != "VerificationDecision":
            continue
        if node.args:
            chosen |= _string_branches(node.args[0])
    declared = set(CHANNELS["job_summary"].scale)
    assert chosen == declared, (
        f"evaluate_verification returns {sorted(chosen)}, job_summary declares "
        f"{sorted(declared)} — the status the worker persists into the summary "
        "moved without the channel moving with it"
    )


def test_notify_announces_exactly_the_words_it_can_be_handed() -> None:
    """Both spellings of one word, in one place: NEEDS REVIEW vs NEEDS_REVIEW."""
    from integrations.notify.templates import TERMINAL_VERDICTS, normalize_verdict

    handed = set(CHANNELS["job_summary"].scale) | set(CHANNELS["report_verdict"].scale)
    assert {normalize_verdict(v) for v in handed} == set(TERMINAL_VERDICTS), (
        f"TERMINAL_VERDICTS {sorted(TERMINAL_VERDICTS)} != normalised "
        f"summary+report {sorted(normalize_verdict(v) for v in handed)} — a "
        "verdict no caller can pass is a dead announcement, and a verdict a "
        "caller can pass is one that silently never notifies"
    )


def test_every_check_run_conclusion_word_is_a_legal_job_status() -> None:
    tree = ast.parse((REPO / "integrations/github_checks.py").read_text(encoding="utf-8"))
    mapped: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "conclusion_for_verdict":
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Dict):
                keys = [k.value for k in sub.keys if isinstance(k, ast.Constant)]
                if "VERIFIED" in keys:
                    mapped = {str(k) for k in keys}
    statuses = set(CHANNELS["job_status"].scale)
    assert mapped, "conclusion_for_verdict's map was not found — probe broken"
    assert mapped <= statuses, (
        f"conclusion_for_verdict maps {sorted(mapped - statuses)} which is not a "
        "state-machine status — a Check Run would announce a word no job can hold"
    )
    assert set(CHANNELS["job_summary"].scale) <= mapped, (
        "every summary verdict must reach GitHub with its own conclusion, not "
        "the `.get(verdict, 'neutral')` default"
    )


def test_the_accept_gloss_covers_the_declared_accept_scale() -> None:
    declared = set(CHANNELS["accept"].scale)
    util = _web_text("apps/web/src/agent/util.ts")
    covered = _ts_equality_tokens(util, "export function acceptVerdictLabel")
    assert declared <= covered, (
        f"acceptVerdictLabel has no branch for {sorted(declared - covered)} — the "
        "projection can emit it and the console would fall back to a mute label"
    )


# ─── reverse controls: the scanner must measure, not match text ─────────────


def test_a_mention_in_a_comment_or_docstring_is_not_a_value() -> None:
    hits = scan_source(
        '"""verdict: "PHANTOM" and verdict="PHANTOM"."""\n'
        'x = 1  # verdict = "PHANTOM"\n',
        "ghost.py",
    )
    assert hits == [], [str(h) for h in hits]


def test_a_real_write_in_an_unowned_file_is_reported() -> None:
    hits = scan_source('row = {"verdict": "PHANTOM"}\n', "ghost.py")
    assert [(h.value, h.shape) for h in hits] == [("PHANTOM", "dict-key")]
    assert _channel_for("ghost.py") is None, "an unowned file must be reported"


def test_a_ternary_producer_is_opaque_and_a_call_is_too() -> None:
    """A conditional writes words this gate must not pretend to have read."""
    ternary = scan_source('verdict = "ALPHA" if flag else "BETA"\n', "ghost.py")
    assert [(h.value, h.shape) for h in ternary] == [(None, "assign")]
    call = scan_source("verdict = compute()\n", "ghost.py")
    assert [(h.value, h.shape) for h in call] == [(None, "assign")]
    # The one place branches are read on purpose, because the channel's words
    # exist nowhere else: the production decision inside evidence/verdict.py.
    decision = ast.parse(
        'status = "ALPHA" if errors else "BETA" if reasons else "GAMMA"\n'
    )
    assert _string_branches(decision.body[0].value) == {"ALPHA", "BETA", "GAMMA"}
