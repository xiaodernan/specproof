"""#87 — `evidence_type` gets a declared domain, and both ends are reconciled.

`findings.evidence_type` is a plain ``VARCHAR(64)`` (infra/mysql/migrations/0001),
so unlike `severity` there is no ENUM to reconcile against. Measured before this
gate existed:

- the Web glossary (`ui/toneMap.ts` `EVIDENCE_CN`) named ``runtime_test``,
  ``static``, ``differential`` and ``review`` — no emitter produces any of them;
- six kinds the pipeline does write had no word at all, so they reached a
  reviewer as raw English (`constitution_check`, `checker_failed`,
  `java_source_diff`, `probe_differential`, `base_pass_head_fail`,
  `differential_execution`); and a seventh only as a fallback default
  (`review_court.py:175`'s ``sf.get("evidence_type", "static_analysis")``).

`agent/evidence_kinds.py` is now the declaration. Producers are still literals
(rewriting a dozen call sites is riskier than the drift it prevents), so the
*gate* is what makes the declaration authoritative: literals must be declared,
declarations must be produced, and the Web glossary must equal the declaration.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECLARATION = REPO / "agent" / "evidence_kinds.py"
TONEMAP = REPO / "apps" / "web" / "src" / "ui" / "toneMap.ts"

PRODUCER_PACKAGES = ("agent", "api", "craft", "cli", "storage", "ops", "integrations")
_FIELD = "evidence_type"
_KEY_RE = re.compile(r'^\s*"?([a-z_][a-z0-9_]*)"?\s*:', re.M)


def declared_kinds() -> frozenset[str]:
    tree = ast.parse(DECLARATION.read_text(encoding="utf-8"))
    for node in tree.body:
        # EVIDENCE_KINDS is annotated (`Final[frozenset[str]]`), so it is an
        # AnnAssign — probing only ast.Assign would find nothing and read as
        # "the declaration is missing".
        target = (
            node.targets[0]
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            else getattr(node, "target", None)
        )
        value = getattr(node, "value", None)
        if not (isinstance(target, ast.Name) and target.id == "EVIDENCE_KINDS"):
            continue
        if isinstance(value, ast.Call):
            values: set[str] = set()
            for arg in value.args:
                if isinstance(arg, ast.Set | ast.List | ast.Tuple):
                    values |= {e.value for e in arg.elts if isinstance(e, ast.Constant)}
            assert values, "EVIDENCE_KINDS parsed but empty — the probe is broken"
            return frozenset(values)
    raise AssertionError("no EVIDENCE_KINDS assignment found in agent/evidence_kinds.py")


def _literals(node: ast.expr | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Call):
        # `sf.get("evidence_type", "static_analysis")` — the default is a value
        # the column can hold, so a scan that stops at the Call loses a
        # producer. Only `.get(<this field>, default)` counts: taking every
        # string argument would report the key itself ("evidence_type") as if
        # it were a kind, and an empty default is an absent value, not a kind
        # (the UI renders it as a dash).
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == _FIELD
        ):
            return {
                a.value
                for a in node.args[1:]
                if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value
            }
        return set()
    if isinstance(node, ast.Dict):
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if "enum" in keys:
            return {
                v
                for k, val in zip(node.keys, node.values, strict=True)
                if isinstance(k, ast.Constant) and k.value == "enum"
                for v in _literals(val)
            }
        return set().union(*(_literals(v) for v in node.values)) if node.values else set()
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return set().union(*(_literals(e) for e in node.elts)) if node.elts else set()
    if isinstance(node, ast.IfExp):
        return _literals(node.body) | _literals(node.orelse)
    return set()


def produced_kinds() -> dict[str, set[str]]:
    """`{"file:line shape": values}` for every literal this field can take."""
    hits: dict[str, set[str]] = {}
    for pkg in PRODUCER_PACKAGES:
        for path in sorted((REPO / pkg).rglob("*.py")):
            if path == DECLARATION:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(REPO).as_posix()
            for node in ast.walk(tree):
                line = getattr(node, "lineno", 0)
                shape = ""
                values: set[str] = set()
                if isinstance(node, ast.Dict):
                    for k, v in zip(node.keys, node.values, strict=True):
                        if isinstance(k, ast.Constant) and k.value == _FIELD:
                            shape, values = "dict-key", _literals(v)
                elif isinstance(node, ast.keyword) and node.arg == _FIELD:
                    shape, values = "kwarg", _literals(node.value)
                elif isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == _FIELD for t in node.targets
                ):
                    shape, values = "assign", _literals(node.value)
                elif (
                    isinstance(node, ast.Compare)
                    and isinstance(node.left, ast.Name)
                    and node.left.id == _FIELD
                ):
                    found = set()
                    for comp in node.comparators:
                        found |= _literals(comp)
                    shape, values = "compare", found
                values = {v for v in values if v}
                if shape and values:
                    hits.setdefault(f"{rel}:{line} {shape}", set()).update(values)
    return hits


def glossed_kinds() -> set[str]:
    text = TONEMAP.read_text(encoding="utf-8")
    _, _, rest = text.partition("EVIDENCE_CN: Record<string, string> = {")
    assert rest, "EVIDENCE_CN map not found in ui/toneMap.ts — the probe is broken"
    body, _, _ = rest.partition("\n};")
    return set(_KEY_RE.findall(body))


def test_the_gate_reads_three_real_sides() -> None:
    assert len(declared_kinds()) >= 7
    assert produced_kinds(), "no evidence_type producer site parsed"
    assert glossed_kinds() >= {"self_test_diff"}


def test_every_kind_a_producer_writes_is_declared() -> None:
    declared = declared_kinds()
    undeclared = {
        f"{site} -> {sorted(values - declared)}"
        for site, values in produced_kinds().items()
        if values - declared
    }
    assert not undeclared, (
        "evidence_type values with no place in agent/evidence_kinds.py:\n  "
        + "\n  ".join(sorted(undeclared))
    )


def test_no_declared_kind_is_wished_for() -> None:
    produced: set[str] = set()
    for values in produced_kinds().values():
        produced |= values
    dead = declared_kinds() - produced
    assert not dead, (
        f"EVIDENCE_KINDS declares kinds nothing writes: {sorted(dead)} — a "
        "declaration of values nobody produces is hope, not a vocabulary"
    )


def test_the_web_glossary_equals_the_declared_domain() -> None:
    declared, glossed = set(declared_kinds()), glossed_kinds()
    assert glossed == declared, (
        f"words with no value: {sorted(glossed - declared)}; "
        f"values shown to a reviewer as raw English: {sorted(declared - glossed)}"
    )


def test_a_failing_checker_is_never_glossed_as_clean() -> None:
    """`checker_failed` must not read as "checked, nothing found"."""
    text = TONEMAP.read_text(encoding="utf-8")
    line = next(
        (raw for raw in text.splitlines() if raw.strip().startswith("checker_failed:")),
        "",
    )
    assert line, "checker_failed has no gloss at all"
    assert "未验证" in line or "不等于没有问题" in line, (
        f"checker_failed gloss hides that no result was produced: {line}"
    )
