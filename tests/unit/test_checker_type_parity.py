"""#90 — `checker_type` is consistent today, and now that is checked, not believed.

An earlier hand-written note in `docs/operations/DRILLS.md` claimed the Web
glossary named a `constitution` checker that nothing produced. That claim came
from a scan that looked only at dict literals, and it was wrong in both
directions: `agent/contracts/compiler.py::family_id_for` branches on
`checker_type == "constitution"` (so the value is part of the model even though
no dict literal writes it), while the same scan missed `tests`. This file
replaces the assertion with a measurement that reads the four shapes the value
actually arrives through, and fails if either side drifts.

Shapes covered: a dict key, a keyword argument, an assignment to a name, and a
comparison against the name (the `family_id_for` chain). A value that only ever
appears in prose (a JSON-schema `enum`, a docstring) is deliberately excluded by
`_literal_strings`' rule of reading values, not keys.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TONEMAP = REPO / "apps" / "web" / "src" / "ui" / "toneMap.ts"
COMPILER = REPO / "agent" / "contracts" / "compiler.py"

PRODUCER_PACKAGES = ("agent", "api", "cli", "storage", "ops", "craft")
_FIELD = "checker_type"
_KEY_RE = re.compile(r'^\s*"?([a-z_][a-z0-9_]*)"?\s*:', re.M)


def _values(node: ast.expr | None) -> set[str]:
    if node is None:
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value} if node.value != _FIELD else set()
    if isinstance(node, ast.Dict):
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if "enum" in keys:
            return {
                v
                for k, val in zip(node.keys, node.values, strict=True)
                if isinstance(k, ast.Constant) and k.value == "enum"
                for v in _values(val)
            }
        return set().union(*(_values(v) for v in node.values)) if node.values else set()
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return set().union(*(_values(e) for e in node.elts)) if node.elts else set()
    if isinstance(node, ast.Call):
        return set().union(*(_values(a) for a in node.args)) if node.args else set()
    if isinstance(node, ast.BinOp):
        return _values(node.left) | _values(node.right)
    if isinstance(node, ast.BoolOp):
        return set().union(*(_values(v) for v in node.values))
    if isinstance(node, ast.IfExp):
        return _values(node.body) | _values(node.orelse)
    return set()


def _field_values(node: ast.AST) -> set[str]:
    """Values this node assigns or tests against `checker_type`, in any of the
    four shapes the field actually moves through."""
    if isinstance(node, ast.keyword) and node.arg == _FIELD:
        return _values(node.value)
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == _FIELD for t in node.targets
    ):
        return _values(node.value)
    if (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == _FIELD
    ):
        return set().union(*(_values(c) for c in node.comparators))
    if isinstance(node, ast.Dict):
        return {
            v
            for k, value in zip(node.keys, node.values, strict=True)
            if isinstance(k, ast.Constant) and k.value == _FIELD
            for v in _values(value)
        }
    return set()


def produced_checkers() -> set[str]:
    out: set[str] = set()
    for pkg in PRODUCER_PACKAGES:
        for path in sorted((REPO / pkg).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                out |= _field_values(node)
    out.discard("")
    return out


def type_rule_checkers() -> set[str]:
    """The first element of every `_TYPE_RULES` row: the compiler's own table."""
    tree = ast.parse(COMPILER.read_text(encoding="utf-8"))
    for node in tree.body:
        target = (
            node.targets[0]
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            else getattr(node, "target", None)
        )
        value = getattr(node, "value", None)
        if (
            isinstance(target, ast.Name)
            and target.id == "_TYPE_RULES"
            and isinstance(value, ast.List)
        ):
            rules = {
                element.elts[0].value
                for element in value.elts
                if isinstance(element, ast.Tuple)
                and element.elts
                and isinstance(element.elts[0], ast.Constant)
                and isinstance(element.elts[0].value, str)
            }
            assert rules, "_TYPE_RULES parsed empty — probe broken"
            return rules
    raise AssertionError("no _TYPE_RULES list found in agent/contracts/compiler.py")


def web_checkers() -> set[str]:
    text = TONEMAP.read_text(encoding="utf-8")
    _, _, rest = text.partition("CHECKER_CN: Record<string, string> = {")
    assert rest, "CHECKER_CN not found in ui/toneMap.ts — probe broken"
    body, _, _ = rest.partition("\n};")
    keys = set(_KEY_RE.findall(body))
    assert keys, "CHECKER_CN parsed empty — probe broken"
    return keys


def test_the_compiler_table_is_a_subset_of_what_the_code_can_emit() -> None:
    missing = type_rule_checkers() - produced_checkers()
    assert not missing, (
        f"_TYPE_RULES can produce {sorted(missing)} that the scan found nowhere — "
        "the scanner needs the new shape, not the document a new excuse"
    )


def test_the_web_glossary_equals_the_checker_vocabulary() -> None:
    produced, glossed = produced_checkers(), web_checkers()
    assert glossed == produced, (
        f"words with no value in the product: {sorted(glossed - produced)}; "
        f"checkers shown to a reviewer as raw English: {sorted(produced - glossed)}"
    )
