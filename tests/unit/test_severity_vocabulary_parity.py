"""#81 — one severity vocabulary, reconciled against every place that claims one.

The Web UI, the MySQL columns, the HTTP contract and the pipeline each named
their own set of severities, and none of them agreed:

- `apps/web/src/ui/toneMap.ts` glossed `INFO`, a value no column can store and
  no producer emits — a badge that can never appear;
- the same file had NO word for `NEEDS_CONFIRMATION`, which `findings.severity`
  is defined to hold, so a legal finding rendered as 未知 UNKNOWN with no hint;
- `pages/JobDetail.tsx` kept a private rank map with CRITICAL/HIGH/MEDIUM/LOW
  (none of which exist anywhere else) while omitting NEEDS_CONFIRMATION, so the
  comment above it ("the canonical enum values are normalized into a rank")
  was false about its own table;
- the two severities the pipeline really emits but cannot store — `NONE` from a
  crashing checker, `ERROR` from counterexample generation — also rendered as
  未知 UNKNOWN, the same words used for a typo, hiding the most actionable
  event on the page.

Like `tests/unit/test_progress_event_labels.py`, both sides are parsed from
their sources rather than typed out here by hand: a hand-copied expectation
would only ever re-assert what the author believed.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO / "infra" / "mysql" / "migrations"
FEEDBACK_ROUTE = REPO / "api" / "routes" / "feedback.py"
TONEMAP = REPO / "apps" / "web" / "src" / "ui" / "toneMap.ts"
WEB_SRC = REPO / "apps" / "web" / "src"

#: Packages whose finding dicts are user-visible. scripts/ and tests/ are out:
#: they build fixtures, they do not define what a review can contain.
PRODUCER_PACKAGES = ("agent", "craft", "cli", "api", "storage", "ops", "integrations")

_TABLE_RE = re.compile(
    r"^\s*(?:CREATE TABLE(?: IF NOT EXISTS)?|ALTER TABLE)\s+(\w+)", re.I | re.M
)
_ENUM_RE = re.compile(r"\b(\w+)\s+(?:\w+\s+)*?ENUM\(([^)]*)\)", re.I | re.S)
_ENTRY_RE = re.compile(
    r'^\s*"?([A-Z][A-Z_0-9]*)"?\s*:\s*\{(.*)\}\s*,?\s*$'
)
_STOREABLE_RE = re.compile(r"storeable:\s*(true|false)")
_SEVERITY_PATTERN_RE = re.compile(
    r'severity:\s*str\s*=\s*Field\(pattern="\^\(([^)]*)\)\$"'
)


def enum_columns() -> dict[str, set[str]]:
    """`{"table.column": values}` for every MySQL ENUM in the migrations.

    Whole-file regexes with a migration-ordered override: a later ALTER TABLE
    MODIFY wins over the CREATE TABLE it replaces, which is how the job-status
    enum grew from 8 to 10 values.
    """
    found: dict[str, set[str]] = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        tables = [(m.start(), m.group(1)) for m in _TABLE_RE.finditer(text)]
        for m in _ENUM_RE.finditer(text):
            table = next(
                (name for start, name in reversed(tables) if start < m.start()), ""
            )
            values = {v.strip().strip("'") for v in m.group(2).split(",")}
            found[f"{table}.{m.group(1)}"] = values
    return found


def stored_severities() -> set[str]:
    columns = enum_columns()
    finding = columns.get("findings.severity")
    feedback = columns.get("finding_feedback.severity")
    assert finding, "findings.severity ENUM not parsed — the probe is broken"
    assert feedback, "finding_feedback.severity ENUM not parsed — the probe is broken"
    assert finding == feedback, (
        "a vote could be stored for a severity the finding row itself "
        f"cannot hold: {sorted(finding ^ feedback)}"
    )
    return finding


def api_pattern_severities() -> set[str]:
    text = FEEDBACK_ROUTE.read_text(encoding="utf-8")
    match = _SEVERITY_PATTERN_RE.search(text)
    assert match, "no severity pattern= found in api/routes/feedback.py — probe broken"
    return set(match.group(1).split("|"))


def glossed_severities() -> dict[str, bool]:
    """`{token: storeable}` from ui/toneMap.ts's SEVERITIES table."""
    text = TONEMAP.read_text(encoding="utf-8")
    _, _, rest = text.partition("SEVERITIES: Record<string, SeveritySpec> = {")
    body, _, _ = rest.partition("\n};")
    out: dict[str, bool] = {}
    for line in body.splitlines():
        entry = _ENTRY_RE.match(line)
        if not entry:
            continue
        flag = _STOREABLE_RE.search(entry.group(2))
        assert flag, f"SEVERITIES.{entry.group(1)} has no storeable flag"
        for field in ("rank:", "cls:", "label:", "hint:"):
            assert field in entry.group(2), f"SEVERITIES.{entry.group(1)} lacks {field}"
        out[entry.group(1)] = flag.group(1) == "true"
    return out


def _literals(node: ast.expr | None) -> set[str]:
    """String literals reachable as *values* under this node.

    A nested dict is a JSON-schema declaration, not a value: only its `enum`
    key names a domain. Without that rule the schema in
    `cli/specproof/commands/baseline.py` reported "string" and "type" as
    severities the UI must gloss, which would have trained the gate to be
    ignored. f-strings yield nothing — a composed value is not a vocabulary
    member.
    """
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.Dict):
        out: set[str] = set()
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if "enum" in keys:
            # A schema fragment declares its domain under `enum`; the rest of
            # that dict is JSON-Schema prose ("type": "string", ...).
            for k, v in zip(node.keys, node.values, strict=True):
                if isinstance(k, ast.Constant) and k.value == "enum":
                    out |= _literals(v)
            return out
        for v in node.values:
            if isinstance(v, ast.Dict):
                continue
            out |= _literals(v)
        return out
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return set().union(*(_literals(e) for e in node.elts))
    if isinstance(node, ast.IfExp):
        return _literals(node.body) | _literals(node.orelse)
    return set()


#: Keys that mark a dict as a finding the verification pages render (see the
#: Finding interface in apps/web/src/api.ts, which mirrors that shape). `craft/`
#: builds a different finding shape — file/line/kind/pattern, with no
#: type/location/contract_id — and the console renders it without a severity at
#: all, so its CRITICAL/HIGH tokens are not producers of this vocabulary.
#: That omission is its own defect, tracked as its own work item.
_FINDING_MARKERS = (
    "evidence_type", "contract_id", "confidence", "id", "type", "location",
)


def emitted_severities() -> dict[str, set[str]]:
    """Values assigned to a `severity` by first-party code, keyed by `file:line`.

    Only verification-shaped findings count: a dict must carry `severity`
    *and* one of the keys the verification pages render. That is what excludes
    craft's canary/gate dicts (documented above) instead of silently widening
    the vocabulary to whatever a second lane invented.
    """
    hits: dict[str, set[str]] = {}
    for pkg in PRODUCER_PACKAGES:
        for path in sorted((REPO / pkg).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(REPO).as_posix()
            for node in ast.walk(tree):
                values: set[str] = set()
                line = getattr(node, "lineno", 0)
                if isinstance(node, ast.Dict):
                    keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                    if "severity" in keys and keys.isdisjoint(_FINDING_MARKERS):
                        continue
                    for k, v in zip(node.keys, node.values, strict=True):
                        if isinstance(k, ast.Constant) and k.value == "severity":
                            values |= _literals(v)
                elif isinstance(node, ast.keyword) and node.arg == "severity":
                    values |= _literals(node.value)
                if values:
                    hits[f"{rel}:{line}"] = values
    return hits


def emitted_value_set() -> set[str]:
    out: set[str] = set()
    for values in emitted_severities().values():
        out |= values
    return out


def test_the_probe_found_a_real_vocabulary_on_both_sides() -> None:
    """A gate that silently parses nothing is greener than a bug."""
    assert len(stored_severities()) >= 4
    assert len(glossed_severities()) >= 4
    assert emitted_value_set(), "no severity emission site parsed"


def test_every_storable_severity_has_a_word_in_the_ui() -> None:
    stored = stored_severities()
    gloss = glossed_severities()
    missing = {s for s, storeable in gloss.items() if storeable} ^ stored
    assert not missing, (
        "the UI's storeable set and findings.severity disagree: "
        f"{sorted(missing)} — a legal value shown as 未知 is a user who cannot "
        "act, a gloss for an unstorable value is a badge that never appears"
    )


def test_no_ui_word_names_a_severity_the_platform_cannot_produce() -> None:
    """The reverse direction: dead vocabulary is decay, not a safety margin."""
    producible = {s for s, storeable in glossed_severities().items() if storeable}
    unknown = set(glossed_severities()) - producible - emitted_value_set()
    assert not unknown, (
        f"toneMap.ts glosses severities nothing can emit: {sorted(unknown)}"
    )


def test_every_severity_the_pipeline_emits_has_a_word_in_the_ui() -> None:
    emitted = emitted_value_set()
    unexplained = emitted - set(glossed_severities())
    assert not unexplained, (
        f"the pipeline emits severities the UI would label 未知: {sorted(unexplained)}"
    )


def test_the_http_contract_accepts_exactly_what_the_column_stores() -> None:
    stored, accepted = stored_severities(), api_pattern_severities()
    assert accepted == stored, (
        "POST /feedback accepts a severity the column cannot store (500 on "
        f"insert) or refuses one it holds: {sorted(accepted ^ stored)}"
    )


def test_the_web_keeps_no_private_copy_of_the_severity_vocabulary() -> None:
    """toneMap.ts is the only file in apps/web allowed to enumerate severities.

    The private JobDetail rank map is exactly what this forbids. The pattern
    matches a token in *vocabulary position* — a record key, a switch case, a
    list element — because that is what a second definition of the set looks
    like; prose inside the ui-kit showcase (`BLOCKER ×1`, a demo toast title)
    names one value and is not a vocabulary.
    """
    vocabulary_position = re.compile(
        r'(?:^|[{,\[]\s*)"?BLOCKER"?\s*:|case\s+"BLOCKER"|\[\s*"BLOCKER"'
    )
    offenders: list[str] = []
    for path in sorted(WEB_SRC.rglob("*.ts*")):
        if path == TONEMAP or ".test." in path.name:
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("//", "*", "/*")):
                continue
            if vocabulary_position.search(stripped):
                offenders.append(
                    f"{path.relative_to(REPO).as_posix()}:{n}: {stripped[:90]}"
                )
    assert not offenders, (
        "second private severity vocabulary (import severityPill/severityRank/"
        f"SEVERITY_STOREABLE from ../ui instead):\n  {'\n  '.join(offenders)}"
    )
