"""#171 — one matrix-result vocabulary, reconciled with the rule that produces it.

`agent/matrix_policy.py::_RESULT_PRIORITY` is what a matrix row's `result` can
hold: `_merge_verdict` returns either a key of that table or its own default,
and `agent/nodes/build_matrix.py` then counts the matrix by comparing rows
against those same words. Four other places enumerate the vocabulary, and before
this gate nothing compared any of them:

- `apps/web/src/pages/Matrix.tsx` had a private `RESULT` caption map;
- `apps/web/src/ui/toneMap.ts` glossed the tones;
- `evidence/report.py` maps a result to the HTML row class;
- `evidence/verdict_channels.py` declares the scale for the channel registry.

Two failures were live at HEAD, one per direction:

1. **A word with no value.** Both Web copies glossed `DEGRADED`
   ("检查受限" / neutral). No producer in the pipeline ever writes that word into
   a matrix result — it belongs to a different scale, `/api/v1/health`'s
   `degraded`, which `healthStatusLabel` translates here already. So the badge
   could never appear, and its wording taught the page a documented state
   ("the run was limited") that this channel never reports. That is the same
   migration `evidence/verdict_channels.py` records for status words entering a
   verdict vocabulary.
2. **A value with no shared reading.** The caption and the tone were two lists
   that happened to agree, so adding a fourth verdict to the merge rule would
   need edits in four files with nothing saying which is authoritative — while
   the page's four StatCards (the three counting comparisons) would silently
   stop adding up.

So the vocabulary is read from the declaration that produces it, every consumer
is read from its own source, and both directions are asserted on each side: a
missing word is a reader who cannot act, and a dead word is a badge that can
never appear. `Matrix.tsx` now imports the caption instead of keeping a list,
and the scan at the bottom is what keeps a new page from starting its own copy.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MATRIX_POLICY = REPO / "agent" / "matrix_policy.py"
BUILD_MATRIX = REPO / "agent" / "nodes" / "build_matrix.py"
REPORT = REPO / "evidence" / "report.py"
CHANNELS = REPO / "evidence" / "verdict_channels.py"
WEB_SRC = REPO / "apps" / "web" / "src"
TONEMAP = WEB_SRC / "ui" / "toneMap.ts"

#: The tokens this channel owns. `DEGRADED` stays in the list on purpose: it is
#: the word that must NOT appear in a result vocabulary, so the scan below
#: reports it as a vocabulary entry wherever it is enumerated.
_RESULT_TOKENS = ("PASS", "FAIL", "UNVERIFIED", "DEGRADED")

_RESULT_TABLE_RE = re.compile(r"_RESULT_PRIORITY\s*:\s*dict\[str,\s*int\]\s*=\s*(\{[^}]*\})")
#: One vocabulary entry per line: `PASS: { ... },` — the shape both the TS map
#: and the Python dicts use, so a multi-line literal cannot hide an entry.
_ENTRY_RE = re.compile(
    r'^\s*"?([A-Z][A-Z_0-9]*)"?\s*:\s*\{[^{}]*\}\s*,?\s*$', re.S
)
_VOCABULARY_LINE_RE = re.compile(
    # A key at the start of a line (with its indentation) OR immediately after
    # an opening brace/comma: a one-line map (`const RESULT = { PASS: "...",
    # FAIL: "..." }`) is the shape the private copy actually had at HEAD, and
    # anchoring only at line start let that whole vocabulary walk past unseen.
    r'(?:^\s*|[{,]\s*)"?(?:' + "|".join(_RESULT_TOKENS) + r')"?\s*:'
)


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def authoritative_results() -> set[str]:
    """The keys of `_RESULT_PRIORITY` — the domain `_merge_verdict` returns from.

    Parsed as source instead of imported: the declaration is the fact being
    checked, and importing the module drags the LangGraph-shaped package chain
    into a vocabulary gate for no benefit.
    """
    match = _RESULT_TABLE_RE.search(_source(MATRIX_POLICY))
    assert match, "_RESULT_PRIORITY declaration not found — the probe is broken"
    table = ast.literal_eval(match.group(1))
    assert isinstance(table, dict) and table, "_RESULT_PRIORITY parsed to nothing"
    return {k for k in table if isinstance(k, str)}


def merge_default() -> str:
    """The literal `_merge_verdict` seeds `best` with.

    A fourth way a word enters the vocabulary that no table key proves: if the
    default were ever spelled outside the table, the merge could hand every
    consumer a word its own domain does not hold.
    """
    tree = ast.parse(_source(MATRIX_POLICY))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_merge_verdict":
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Assign)
                    and any(
                        isinstance(t, ast.Name) and t.id == "best" for t in inner.targets
                    )
                    and isinstance(inner.value, ast.Constant)
                    and isinstance(inner.value.value, str)
                ):
                    return inner.value.value
    raise AssertionError("_merge_verdict never seeds `best` with a literal")


def _dict_keys(source: str, name: str, path: Path) -> dict[str, str]:
    """`{token: entry-line}` for a one-entry-per-line `const` literal named
    `name`.

    The declaration is matched at a line start and must begin with `const`:
    prose that only mentions the map's name in passing is what first made this
    probe read a JSDoc line instead of the table, and a comment is not a
    vocabulary.
    """
    match = re.search(rf"^(?:export\s+)?const\s+{name}\b[^=]*=\s*\{{", source, re.M)
    assert match, f"const {name} = {{ ... }} not found in {path.name} — probe broken"
    body = source[match.end():]
    end = body.find("\n}")
    assert end > 0, f"{name} in {path.name} has no closing brace — probe broken"
    entries: dict[str, str] = {}
    for line in body[:end].splitlines():
        parsed = _ENTRY_RE.match(line)
        if parsed:
            entries[parsed.group(1)] = line.strip()
    assert entries, f"{name} in {path.name} parsed to no entries — probe broken"
    return entries


def web_result_states() -> dict[str, str]:
    """`RESULT_STATES` in toneMap.ts: one row per result, tone + caption."""
    return _dict_keys(_source(TONEMAP), "RESULT_STATES", TONEMAP)


def report_row_classes() -> dict[str, str]:
    """The HTML report's `result_class` lookup."""
    for node in ast.walk(ast.parse(_source(REPORT))):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "result_class" for t in node.targets):
            continue
        value = node.value
        # The shipped shape is `{...}.get(key, "")`, so the literal is the call's
        # receiver, not the value: reading only `ast.Dict` here would have found
        # nothing and left the whole consumer unchecked.
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
            value = value.func.value
        assert isinstance(value, ast.Dict), "result_class is not a dict literal"
        return {
            k.value: "row class"
            for k in value.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
    raise AssertionError("result_class lookup not found in evidence/report.py")


def matrix_count_comparisons() -> set[str]:
    """Words `build_matrix.py` counts rows by — the matrix page's four StatCards.

    A word the counting site forgets still occupies a row while vanishing from
    the totals, which makes "passed + failed + unverified == total" false on the
    page readers trust most.
    """
    out: set[str] = set()
    for node in ast.walk(ast.parse(_source(BUILD_MATRIX))):
        if not isinstance(node, ast.Compare) or len(node.comparators) != 1:
            continue
        left = node.left
        if (
            isinstance(left, ast.Subscript)
            and isinstance(left.value, ast.Name)
            and left.value.id == "row"
            and isinstance(left.slice, ast.Constant)
            and left.slice.value == "result"
            and isinstance(node.ops[0], ast.Eq)
            and isinstance(node.comparators[0], ast.Constant)
            and isinstance(node.comparators[0].value, str)
        ):
            out.add(node.comparators[0].value)
    assert len(out) >= 3, f"only {sorted(out)} counting comparisons parsed — probe broken"
    return out


def _string_literals(node: ast.expr) -> set[str]:
    """Every string literal inside a set/list/tuple literal or a `frozenset(...)`
    call around one."""
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.Call):
        return set().union(*(_string_literals(a) for a in node.args))
    if isinstance(node, ast.Set | ast.List | ast.Tuple):
        return set().union(*(_string_literals(e) for e in node.elts))
    return set()


def channel_scale() -> set[str]:
    """The `matrix_row` scale declared in the verdict-channel registry."""
    for node in ast.walk(ast.parse(_source(CHANNELS))):
        if not (
            isinstance(node, ast.Call)
            and getattr(node.func, "id", "") == "VerdictChannel"
            and any(
                k.arg == "key"
                and isinstance(k.value, ast.Constant)
                and k.value.value == "matrix_row"
                for k in node.keywords
            )
        ):
            continue
        for keyword in node.keywords:
            if keyword.arg == "scale":
                words = _string_literals(keyword.value)
                assert words, "matrix_row scale parsed to nothing — probe broken"
                return words
    raise AssertionError("matrix_row channel not found in verdict_channels.py")


def web_vocabulary_sites_outside_ui() -> list[str]:
    """Every apps/web file that enumerates result words as a vocabulary.

    Position decides what counts: a record key (`PASS: "..."`) defines a set,
    while `row.result === "PASS"` names one observation and a fixture value
    names one row. Only the shared ui/ map may define the set, so this returns
    the offenders rather than a number the caller has to interpret.
    """
    offenders: list[str] = []
    sites = 0
    for path in sorted(WEB_SRC.rglob("*.ts*")):
        if ".test." in path.name:
            continue
        in_ui = "/ui/" in path.as_posix().replace("\\", "/")
        for n, line in enumerate(_source(path).splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            if _VOCABULARY_LINE_RE.search(line):
                sites += 1
                if not in_ui:
                    offenders.append(
                        f"{path.relative_to(REPO).as_posix()}:{n}: {stripped[:90]}"
                    )
    # The floor is the scan's own denominator: a walk that reaches nothing, or a
    # token list that stops matching anything, would otherwise return an empty
    # offender list and look like the cleanest result in the file.
    assert sites >= 3, (
        f"the web result-vocabulary scan saw {sites} entries — the shared map "
        f"in ui/toneMap.ts alone has {len(authoritative_results())}, so the "
        "scan, not the code, is broken"
    )
    return offenders


# ── the gate ─────────────────────────────────────────────────────────────────

def test_the_probe_found_a_real_vocabulary_on_every_side() -> None:
    """A gate that silently parses nothing is greener than a bug."""
    words = authoritative_results()
    assert words == {"FAIL", "PASS", "UNVERIFIED"}, words
    assert set(web_result_states()) == words
    assert set(report_row_classes()) == words
    assert matrix_count_comparisons() == words
    assert channel_scale() == words


def test_the_merge_cannot_return_a_word_outside_its_own_table() -> None:
    default = merge_default()
    assert default in authoritative_results(), (
        f"_merge_verdict seeds its result with {default!r}, which is not a "
        "_RESULT_PRIORITY key: the merge can hand every consumer a word its "
        "own domain does not hold"
    )


def test_every_result_the_platform_produces_has_a_word_in_the_ui() -> None:
    """The direction that fails when someone adds a fourth verdict."""
    words = authoritative_results()
    consumers = {
        "apps/web/src/ui/toneMap.ts RESULT_STATES": set(web_result_states()),
        "evidence/report.py result_class": set(report_row_classes()),
        "agent/nodes/build_matrix.py counts": matrix_count_comparisons(),
    }
    for site, known in consumers.items():
        missing = words - known
        assert not missing, (
            f"{site} has no entry for {sorted(missing)}: the pipeline produces "
            "it, so a reader sees 未知 / an unstyled row and the totals stop "
            "adding up"
        )


def test_no_ui_word_names_a_result_the_platform_cannot_produce() -> None:
    """The reverse direction: dead vocabulary is decay, not a safety margin."""
    words = authoritative_results()
    consumers = {
        "apps/web/src/ui/toneMap.ts RESULT_STATES": set(web_result_states()),
        "evidence/report.py result_class": set(report_row_classes()),
        "agent/nodes/build_matrix.py counts": matrix_count_comparisons(),
        "evidence/verdict_channels.py matrix_row scale": channel_scale(),
    }
    for site, known in consumers.items():
        dead = known - words
        assert not dead, (
            f"{site} enumerates {sorted(dead)}, which nothing writes into a "
            "matrix result: the badge can never appear, and its wording teaches "
            "a state this channel never reports (DEGRADED is the health scale)"
        )


def test_every_result_state_carries_both_readings() -> None:
    """A token in the map with only a tone is a half-glossed badge.

    The caption is what `resultCaption` renders under the pill and what the
    search box matches, so an entry that forgets it silently makes a real result
    read as 待确认状态 while the pill still looks correct.
    """
    for token, line in sorted(web_result_states().items()):
        assert re.search(r'\bcls:\s*"pill-(?:ok|bad|unverified|mute)"', line), (
            f"RESULT_STATES.{token} has no pill tone: {line}"
        )
        assert re.search(r'\bcaption:\s*"[^"]+"', line), (
            f"RESULT_STATES.{token} has no Chinese caption: {line}"
        )


def test_the_page_imports_the_shared_result_vocabulary() -> None:
    """`Matrix.tsx` renders captions through ui/, it does not keep its own list.

    The second copy is what let `DEGRADED` live in one place and not another; a
    name-based check would not have caught a renamed map, so this reads the
    page's own import and use sites.
    """
    page = _source(WEB_SRC / "pages" / "Matrix.tsx")
    assert re.search(r"\bresultCaption\b", page), (
        "Matrix.tsx no longer imports resultCaption — the caption has moved "
        "back into the page, where the vocabulary can drift again"
    )
    assert not re.search(r"\bconst\s+RESULT\s*[:=]", page), (
        "Matrix.tsx declares a second RESULT vocabulary again"
    )


def test_the_web_keeps_no_second_result_vocabulary_outside_ui() -> None:
    offenders = web_vocabulary_sites_outside_ui()
    assert not offenders, (
        "second private result vocabulary — import resultPill/resultCaption "
        "from ../ui instead:\n  " + "\n  ".join(offenders)
    )
