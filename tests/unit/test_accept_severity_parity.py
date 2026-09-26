"""#86 — the acceptance lane's severity scale is declared and reconciled.

`craft`/`agent/security_scanner.py` write a severity onto every acceptance
finding, and the independent-acceptance console showed those findings as a raw
JSON dump. A raw dump is honest but unreadable, and the scale here is not the
verification platform's `findings.severity` ENUM — so the glossary had to be
built from measurement, not by reusing the other scale.

Both sides are parsed from their sources (the same rule
`tests/unit/test_severity_vocabulary_parity.py` follows): the scanner's pattern
table, the literals craft writes, the constants craft blocks on, and the
`ACCEPT_SEVERITY_CN` record in the Web UI.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DECLARATION = REPO / "craft" / "severity.py"
SCANNER = REPO / "agent" / "security_scanner.py"
CRAFT = REPO / "craft"
TONEMAP = REPO / "apps" / "web" / "src" / "ui" / "toneMap.ts"

_FIELD = "severity"
_KEY_RE = re.compile(r'^\s*"?([A-Z_][A-Z_0-9]*)"?\s*:', re.M)
# Either `BLOCKING_SECRET_SEVERITIES = ("CRITICAL", "HIGH")` or an inline
# `finding["severity"] in ("CRITICAL", "HIGH")` comparison.
_BLOCKING_RE = re.compile(
    r"_SEVERITIES(?:\s*=\s*\(([A-Z_,\" ]*)\)|[^\n]*in \(([A-Z_,\" ]*)\))"
)


def _assigned(node: ast.AST, name: str) -> ast.expr | None:
    for sub in ast.walk(node):
        if isinstance(sub, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in sub.targets
        ):
            return sub.value
        if isinstance(sub, ast.AnnAssign) and getattr(sub.target, "id", "") == name:
            return sub.value
    return None


def _literal_strings(node: ast.expr | None) -> set[str]:
    """Every static string reachable in value position under `node`.

    The field name itself is excluded: `entry.get("severity")` would otherwise
    report "severity" as a severity.
    """
    if node is None:
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return set() if node.value == _FIELD else {node.value}
    if isinstance(node, ast.Dict):
        return set().union(*(_literal_strings(v) for v in node.values)) if node.values else set()
    if isinstance(node, ast.List | ast.Tuple | ast.Set):
        return set().union(*(_literal_strings(e) for e in node.elts)) if node.elts else set()
    if isinstance(node, ast.Call):
        out: set[str] = set()
        for arg in node.args:
            out |= _literal_strings(arg)
        for kw in node.keywords:
            out |= _literal_strings(kw.value)
        return out
    if isinstance(node, ast.BoolOp):
        return set().union(*(_literal_strings(v) for v in node.values))
    if isinstance(node, ast.IfExp):
        return _literal_strings(node.body) | _literal_strings(node.orelse)
    return set()


def scanner_severities() -> set[str]:
    """The third element of every `_SECRET_PATTERNS` row: (regex, name, severity)."""
    tree = ast.parse(SCANNER.read_text(encoding="utf-8"))
    table = _assigned(tree, "_SECRET_PATTERNS")
    assert isinstance(table, ast.List), "_SECRET_PATTERNS is not a list literal — probe broken"
    out: set[str] = set()
    for row in table.elts:
        if isinstance(row, ast.Tuple) and len(row.elts) == 3:
            sev = row.elts[2]
            assert isinstance(sev, ast.Constant) and isinstance(sev.value, str), (
                f"pattern row without a literal severity: {ast.unparse(row)[:60]}"
            )
            out.add(sev.value)
    assert len(out) >= 3, f"only {len(out)} scanner severities parsed — probe broken"
    return out


def craft_severities() -> set[str]:
    """Literals craft assigns to `severity` (dict key, kwarg, parameter default)."""
    out: set[str] = set()
    for path in sorted(CRAFT.rglob("*.py")):
        if path == DECLARATION:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k, v in zip(node.keys, node.values, strict=True):
                    if isinstance(k, ast.Constant) and k.value == _FIELD:
                        out |= _literal_strings(v)
            elif isinstance(node, ast.keyword) and node.arg == _FIELD:
                out |= _literal_strings(node.value)
            elif isinstance(node, ast.FunctionDef):
                args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                defaults = list(node.args.defaults) + list(node.args.kw_defaults)
                for arg, default in zip(reversed(args), reversed(defaults), strict=False):
                    if arg.arg == _FIELD:
                        out |= _literal_strings(default)
    assert out, "no craft severity literal parsed — probe broken"
    return out


def blocking_comparisons() -> set[str]:
    """Severities the gates actually treat as blocking, read from the source."""
    out: set[str] = set()
    for path in sorted(CRAFT.rglob("*.py")):
        if path == DECLARATION:
            continue
        text = path.read_text(encoding="utf-8")
        for match in _BLOCKING_RE.finditer(text):
            group = match.group(1) or match.group(2) or ""
            out |= {t.strip().strip('"') for t in group.split(",") if t.strip()}
    return out


def _declared(constant: str) -> set[str]:
    tree = ast.parse(DECLARATION.read_text(encoding="utf-8"))
    value = _assigned(tree, constant)
    assert value is not None, f"{constant} not found in craft/severity.py"
    literals = {
        e.value
        for node in ast.walk(value)
        if isinstance(node, (ast.Set, ast.List, ast.Tuple))
        for e in node.elts
        if isinstance(e, ast.Constant) and isinstance(e.value, str)
    }
    assert literals, f"{constant} parsed empty — probe broken"
    return literals


def declared_severities() -> set[str]:
    return _declared("ACCEPT_FINDING_SEVERITIES")


def glossed_severities() -> set[str]:
    text = TONEMAP.read_text(encoding="utf-8")
    _, _, rest = text.partition("ACCEPT_SEVERITY_CN: Record<string, string> = {")
    assert rest, "ACCEPT_SEVERITY_CN not found in ui/toneMap.ts — probe broken"
    body, _, _ = rest.partition("\n};")
    return set(_KEY_RE.findall(body))


def test_the_declaration_is_the_union_of_what_the_two_producers_write() -> None:
    produced = scanner_severities() | craft_severities()
    assert declared_severities() == produced, (
        f"declared but never written: {sorted(declared_severities() - produced)}; "
        f"written but undeclared: {sorted(produced - declared_severities())}"
    )


def test_the_web_glossary_equals_the_declared_scale() -> None:
    declared, glossed = declared_severities(), glossed_severities()
    assert glossed == declared, (
        f"words with no value: {sorted(glossed - declared)}; severities the "
        f"console would print untranslated: {sorted(declared - glossed)}"
    )


def fe_blocking() -> set[str]:
    """The list the console colours red — a third copy unless it agrees."""
    text = TONEMAP.read_text(encoding="utf-8")
    _, _, rest = text.partition("ACCEPT_SEVERITY_BLOCKING: string[] = [")
    assert rest, "ACCEPT_SEVERITY_BLOCKING not found in ui/toneMap.ts — probe broken"
    body, _, _ = rest.partition("]")
    return {t.strip().strip('"') for t in body.split(",") if t.strip()}


def test_the_blocking_scale_matches_the_code_that_blocks() -> None:
    declared_blocking = _declared("BLOCKING_ACCEPT_SEVERITIES")
    in_code = blocking_comparisons()
    assert declared_blocking, "BLOCKING_ACCEPT_SEVERITIES parsed empty"
    assert in_code, "no `*_SEVERITIES = (...)` / `in (...)` comparison found in craft"
    assert declared_blocking == in_code, (
        f"craft/severity.py says {sorted(declared_blocking)} block, the code "
        f"compares {sorted(in_code)}"
    )
    assert fe_blocking() == declared_blocking, (
        f"the console marks {sorted(fe_blocking())} as blocking; the gates block "
        f"{sorted(declared_blocking)}"
    )


def test_medium_and_low_say_they_do_not_block() -> None:
    """A reviewer must not be told a MEDIUM finding stops the merge."""
    declared, blocking = declared_severities(), _declared("BLOCKING_ACCEPT_SEVERITIES")
    assert {"MEDIUM", "LOW"} <= declared - blocking, (
        f"MEDIUM/LOW must be non-blocking; blocking set is {sorted(blocking)}"
    )
    text = TONEMAP.read_text(encoding="utf-8")

    def gloss(token: str) -> str:
        return next((raw for raw in text.splitlines() if raw.strip().startswith(f'{token}: "')), "")

    for token in ("MEDIUM", "LOW"):
        assert "不阻断" in gloss(token), f"{token} gloss must say it does not block acceptance"
    for token in sorted(blocking):
        assert "阻断" in gloss(token), f"{token} blocks the gates; its gloss may not hide that"
