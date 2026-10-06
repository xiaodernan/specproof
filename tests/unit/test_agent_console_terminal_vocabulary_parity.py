"""#172 — one Craft-console run-phase vocabulary, reconciled with the API that enforces it.

`api/agent_runtime.py::console_status_label` is the single source of the console
vocabulary (its own docstring says so, and #69 made its tail
`return str(job.status)` so an out-of-vocabulary store status reaches the
browser VERBATIM — "the UI's own unknown handling decides how to show it").
`api/routes/agent_console.py` then enforces the run phase with two frozensets:
`_require_cancellable` and the approvals route refuse on membership in
`_TERMINAL_CONSOLE_STATUSES`.

Before this gate the Web side did not share either fact:

- the terminal triple was hand-copied **five** times
  (`agent/components.tsx` polling stop, `AgentJobDetail` cancel disable,
  `AgentResult` twice — accept panel and result panel — and `AgentToolStream`'s
  header tail), and
- nothing at all implemented the third case #69 promised. With `!terminal` as
  the test, an unrecognized token that really is a finished run (a stale row,
  an older writer) read forever as 「任务还在处理中」 / 「任务尚未进入终态」 — the
  page invented a meaning for a value the runtime deliberately left alone,
  which is the exact defect #69 removed on the backend.

So the vocabulary is read from the declarations that own it, both directions are
asserted per site, the pass-through is checked to still exist (the frontend's
third phase only earns its keep while it does), and the scan at the bottom
charges enumeration *and* comparison positions so a sixth copy or a dead branch
cannot appear quietly.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / "api" / "agent_runtime.py"
CONSOLE = REPO / "api" / "routes" / "agent_console.py"
AGENT_SRC = REPO / "apps" / "web" / "src" / "agent"
UTIL = AGENT_SRC / "util.ts"

#: The whole console vocabulary, in the shape the frontend declares it.
TOKENS = ("PLANNING", "AWAITING_APPROVAL", "EXECUTING", "COMPLETED", "FAILED", "CANCELLED")

_TS_ARRAY_RE = re.compile(
    r"^export const (AGENT_ACTIVE_STATUSES|AGENT_TERMINAL_STATUSES)\b[^=]*=\s*\[(.*?)\]",
    re.S | re.M,
)
_META_KEY_RE = re.compile(r'^\s*"?([A-Z][A-Z_0-9]*)"?\s*:\s*\{', re.M)
#: `job.status === "TOKEN"` — a comparison against THE run's status. Anchoring on
#: any `.status` was over-broad and named other scales as offenders
#: (`gate.status === "passed"`, `line.status === "added"`,
#: `step.status === "approved"`), which are three different vocabularies this
#: console does not own.
_COMPARE_RE = re.compile(r'\bjob\.status\s*[!=]==\s*"([A-Za-z_][A-Za-z_0-9]*)"')


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _string_literals(node: ast.expr) -> set[str]:
    """Every string literal in a `frozenset({...})` / `{...}` / list shape."""
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.Call):
        return set().union(*(_string_literals(a) for a in node.args))
    if isinstance(node, ast.Set | ast.List | ast.Tuple):
        return set().union(*(_string_literals(e) for e in node.elts))
    if isinstance(node, ast.Dict):
        return {
            k.value
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
    if isinstance(node, ast.IfExp):
        # `return "AWAITING_APPROVAL" if job.plan_json else "PLANNING"` — the
        # pending row's two words live in one conditional return, so an
        # expression walker that stops at IfExp reports a smaller console
        # vocabulary than the mapping really has.
        return _string_literals(node.body) | _string_literals(node.orelse)
    return set()


def backend_sets() -> dict[str, set[str]]:
    """`_CANCELLABLE_STATUSES` / `_TERMINAL_CONSOLE_STATUSES`, by name."""
    found: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(_source(CONSOLE))):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in (
                "_CANCELLABLE_STATUSES",
                "_TERMINAL_CONSOLE_STATUSES",
            ):
                found[target.id] = _string_literals(node.value)
    assert len(found) == 2, f"only {sorted(found)} console frozensets parsed — probe broken"
    for name, words in found.items():
        assert words, f"{name} parsed to nothing — probe broken"
    return found


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"function {name} not found")


def console_mapped_tokens() -> set[str]:
    """Tokens `console_status_label` can name — the console vocabulary proper.

    Read from the RETURN statements only: the store words (`pending`, `running`,
    …) live in the `if` tests, and folding them in would let this gate pass a UI
    that labels store words the browser never sees.
    """
    fn = _function(ast.parse(_source(RUNTIME)), "console_status_label")
    words: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            words |= {w for w in _string_literals(node.value) if w.isupper() or "_" in w}
    assert words, "console_status_label returns no literal token — probe broken"
    return words


def console_passes_unknown_through() -> bool:
    """Whether `return str(job.status)` is still the tail of the mapping.

    The frontend's third phase exists only to serve this line; the gate below
    pairs the two so neither can rot without the other noticing.
    """
    fn = _function(ast.parse(_source(RUNTIME)), "console_status_label")
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Return)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", "") == "str"
            and isinstance(node.value.func, ast.Name)
        ):
            arg = node.value.args[0] if node.value.args else None
            if isinstance(arg, ast.Attribute) and arg.attr == "status":
                return True
    return False


def web_lists() -> dict[str, set[str]]:
    """`AGENT_ACTIVE_STATUSES` / `AGENT_TERMINAL_STATUSES` in agent/util.ts."""
    source = _source(UTIL)
    found: dict[str, set[str]] = {}
    for match in _TS_ARRAY_RE.finditer(source):
        words = set(re.findall(r'"([A-Z_]+)"', match.group(2)))
        assert words, f"{match.group(1)} declared empty — probe broken"
        found[match.group(1)] = words
    assert len(found) == 2, (
        f"only {sorted(found)} phase lists found in util.ts — the declarations "
        "moved or changed shape, so the probe is reading nothing"
    )
    return found


def web_status_meta_keys() -> set[str]:
    """Keys of `AGENT_STATUS_META` — one per line, the shipped shape."""
    source = _source(UTIL)
    start = source.index("export const AGENT_STATUS_META")
    body = source[start: source.index("\n}", start)]
    keys = set(_META_KEY_RE.findall(body))
    assert keys, "AGENT_STATUS_META parsed to no keys — probe broken"
    return keys


def _literal_spans(text: str) -> list[str]:
    """Every balanced `[...]` span in a TS source, newlines included.

    Bracket-balanced rather than line-based: a hand-copied vocabulary is free to
    put one token per line, and a line-anchored scan would let that shape walk
    past unseen (the exact hole the #171 scan had to close).
    """
    spans: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "[":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "]" and depth:
            depth -= 1
            if depth == 0:
                spans.append(text[start : i + 1])
    return spans


def web_vocabulary_copies() -> list[str]:
    """Non-util files enumerating ≥2 console tokens as one literal.

    One token is an observation (`status === "COMPLETED"`); two or more in one
    literal is a vocabulary — and a vocabulary the console owns once, in util.ts.
    """
    offenders: list[str] = []
    sites = 0
    for path in sorted(AGENT_SRC.rglob("*.ts*")):
        if ".test." in path.name:
            continue
        if path == UTIL:
            continue
        text = _source(path)
        for span in _literal_spans(text):
            words = {t for t in TOKENS if f'"{t}"' in span}
            if len(words) >= 2:
                sites += 1
                offenders.append(
                    f"{path.relative_to(REPO).as_posix()}: {sorted(words)} in {span[:70]!r}"
                )
    # The floor is this scan's own denominator: util.ts declares two such
    # literals, so a walk that reaches fewer than two anywhere has read nothing —
    # and "no offenders" would be a green that proves only that.
    util_sites = sum(
        1
        for span in _literal_spans(_source(UTIL))
        if len({t for t in TOKENS if f'"{t}"' in span}) >= 2
    )
    assert util_sites >= 2, (
        f"agent/util.ts itself only shows {util_sites} vocabulary literals — "
        "the scan, not the code, is broken"
    )
    return offenders


def web_comparison_tokens() -> dict[str, set[str]]:
    """Every `job.status` token the agent console sources compare against."""
    per_file: dict[str, set[str]] = {}
    for path in sorted(AGENT_SRC.rglob("*.ts*")):
        if ".test." in path.name:
            continue
        words = set(_COMPARE_RE.findall(_source(path)))
        if words:
            per_file[path.relative_to(REPO).as_posix()] = words
    total = sum(len(v) for v in per_file.values())
    assert total >= 3, (
        f"the comparison scan saw {total} job.status tokens across "
        f"{len(per_file)} files — the pages do branch on the run status, so this "
        "scan is broken"
    )
    return per_file


def unknown_notice_readers() -> list[str]:
    """Non-test sources that actually render `agentUnknownNotice`."""
    readers: list[str] = []
    for path in sorted(AGENT_SRC.rglob("*.ts*")):
        if ".test." in path.name or path == UTIL:
            continue
        if re.search(r"\bagentUnknownNotice\(", _source(path)):
            readers.append(path.relative_to(REPO).as_posix())
    return readers


# ── the gate ─────────────────────────────────────────────────────────────────

def test_the_probe_found_a_real_vocabulary_on_every_side() -> None:
    """A gate that silently parses nothing is greener than a bug."""
    backend = backend_sets()
    lists = web_lists()
    assert backend["_TERMINAL_CONSOLE_STATUSES"] == {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }, backend
    assert backend["_CANCELLABLE_STATUSES"] == {
        "PLANNING",
        "AWAITING_APPROVAL",
        "EXECUTING",
    }, backend
    assert lists["AGENT_TERMINAL_STATUSES"] == {"COMPLETED", "FAILED", "CANCELLED"}
    assert lists["AGENT_ACTIVE_STATUSES"] == {"PLANNING", "AWAITING_APPROVAL", "EXECUTING"}
    assert console_mapped_tokens() == set(TOKENS)
    assert web_status_meta_keys() == set(TOKENS)


def test_the_pages_terminal_set_is_the_one_the_api_enforces() -> None:
    """Both directions: a set that drifts either stops polling a live run or
    declares a running one closed (and hides its 取消 button while the server
    would still honour it)."""
    backend = backend_sets()["_TERMINAL_CONSOLE_STATUSES"]
    frontend = web_lists()["AGENT_TERMINAL_STATUSES"]
    missing = backend - frontend
    extra = frontend - backend
    assert not missing, (
        f"the API refuses cancel/approvals on {sorted(missing)} but agent/util.ts "
        "does not call it terminal: the pages keep polling and promise a result "
        "that already arrived"
    )
    assert not extra, (
        f"agent/util.ts calls {sorted(extra)} terminal, and nothing in "
        "agent_console enforces that: a still-running job is painted as closed "
        "and its controls are disabled"
    )


def test_the_active_set_mirrors_the_declared_cancellable_vocabulary() -> None:
    backend = backend_sets()["_CANCELLABLE_STATUSES"]
    frontend = web_lists()["AGENT_ACTIVE_STATUSES"]
    assert frontend == backend, (
        f"frontend {sorted(frontend)} vs declared {sorted(backend)} — the console "
        "would classify a phase the API never listed as active"
    )


def test_the_two_backend_sets_are_disjoint_and_cover_the_mapping() -> None:
    """A token in both sets makes 终态 and 进行中 the same claim, and a mapped
    token in neither leaves `agentRunPhase` answering 不认识 for a status the
    runtime does know."""
    backend = backend_sets()
    overlap = backend["_CANCELLABLE_STATUSES"] & backend["_TERMINAL_CONSOLE_STATUSES"]
    assert not overlap, f"{sorted(overlap)} is both cancellable and terminal"
    uncovered = console_mapped_tokens() - set().union(*backend.values())
    assert not uncovered, (
        f"console_status_label returns {sorted(uncovered)} which neither frozenset "
        "holds — the pages can only call it 不认识"
    )


def test_the_pass_through_and_the_unknown_branch_stand_together() -> None:
    """#69's promise, pinned from both ends.

    While `console_status_label` forwards an unmapped store status verbatim, the
    console MUST have a third phase and a page must render its wording —
    otherwise the browser answers a value it does not know with 「还在处理中」.
    If the pass-through is ever folded back into a known word, this clause says
    to delete the unknown branch, not to leave a copy no input can reach.
    """
    passes = console_passes_unknown_through()
    readers = unknown_notice_readers()
    assert passes, (
        "console_status_label no longer returns str(job.status) for an unmapped "
        "status — if every store value is now folded into a console word, delete "
        "agentUnknownNotice and the pages' 不认识 branch"
    )
    assert readers, (
        "the runtime can still forward an unmapped status verbatim, but no agent "
        "page renders agentUnknownNotice — the third phase is declared and never "
        "shown, which is the defect #172 removed"
    )


def test_every_mapped_console_token_has_exactly_one_ui_word() -> None:
    """No value without a word, no word without a value."""
    mapped = console_mapped_tokens()
    labels = web_status_meta_keys()
    assert mapped - labels == set(), (
        f"{sorted(mapped - labels)} is returned by console_status_label but has no "
        "entry in AGENT_STATUS_META: the timeline prints a bare English token"
    )
    assert labels - mapped == set(), (
        f"{sorted(labels - mapped)} is glossed in AGENT_STATUS_META but nothing maps "
        "to it — a dead label teaches the reader a state this console never reports"
    )


def test_the_web_keeps_no_second_console_vocabulary() -> None:
    offenders = web_vocabulary_copies()
    assert not offenders, (
        "second private terminal/active vocabulary — import isAgentTerminal / "
        "agentRunPhase from agent/util instead:\n  " + "\n  ".join(offenders)
    )


def test_no_page_compares_a_status_the_console_cannot_emit() -> None:
    """Comparison positions, not just declarations.

    A `job.status` branch on a token the mapping never returns is unreachable,
    and it rots beside the code that replaced it — the shape #170 caught on
    `nextAction`. Other scales are deliberately not charged here: gate, diff-file
    and step statuses are three different vocabularies with their own gates.
    """
    vocabulary = set(TOKENS)
    offenders = [
        f"{name}: {sorted(words - vocabulary)}"
        for name, words in sorted(web_comparison_tokens().items())
        if words - vocabulary
    ]
    assert not offenders, (
        "job.status comparison outside the console vocabulary — the branch can "
        "never fire (or the vocabulary grew without this gate):\n  "
        + "\n  ".join(offenders)
    )
