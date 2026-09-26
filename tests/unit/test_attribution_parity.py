"""#91 — the matrix page's 差异归因 vocabulary is checked, not asserted.

`docs/operations/DRILLS.md` recorded (after #90 corrected an earlier false
measurement) that `attribution` was consistent between producer and glossary but
had no gate. This closes that line: the row-level attribution is decided in
exactly two places, and both are read here rather than transcribed.

Producers measured at f5dacaf:
  * `agent/nodes/build_matrix.py::_ATTRIBUTION_BY_VERDICT` — verdict -> attribution
    (head / base / not_attributed / none);
  * `agent/matrix_policy.py::_merged_attribution` — returns "none"/"unknown"/"head"
    and otherwise passes an entry's own attribution through;
  * `agent/nodes/build_matrix.py` writes the key directly on row entries.

Unlike `checker_type` (#90), this field also needs the return-value shape: the
vocabulary lives in `return` statements inside the functions that decide it, and
a scan of dict keys alone would call `unknown` an orphan glossary word — which is
how the earlier hand measurement went wrong in the first place.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD_MATRIX = REPO / "agent" / "nodes" / "build_matrix.py"
MATRIX_POLICY = REPO / "agent" / "matrix_policy.py"
AGENT_DIR = REPO / "agent"
TONEMAP = REPO / "apps" / "web" / "src" / "ui" / "toneMap.ts"

_FIELD = "attribution"
_KEY_RE = re.compile(r'^\s*"?([a-z_][a-z0-9_]*)"?\s*:', re.M)


def _returns_of_functions_named_like(path: Path) -> set[str]:
    """Literal returns of any function whose name contains `attribution`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or _FIELD not in node.name.lower():
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Return)
                and isinstance(sub.value, ast.Constant)
                and isinstance(sub.value.value, str)
                and sub.value.value
            ):
                out.add(sub.value.value)
    return out


def _table_values(path: Path, table: str) -> set[str]:
    """Values of a module-level dict literal, by variable name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        target = (
            node.targets[0]
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            else getattr(node, "target", None)
        )
        value = getattr(node, "value", None)
        if isinstance(target, ast.Name) and target.id == table and isinstance(value, ast.Dict):
            out = {
                v.value
                for v in value.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value
            }
            assert out, f"{table} parsed empty — probe broken"
            return out
    raise AssertionError(f"no dict literal {table} in {path.name}")


def _dict_key_writes() -> set[str]:
    """Every literal written under the `attribution` key anywhere in agent/."""
    out: set[str] = set()
    for path in sorted(AGENT_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for k, v in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == _FIELD
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, str)
                    and v.value
                ):
                    out.add(v.value)
    return out


def domain() -> set[str]:
    return (
        _table_values(BUILD_MATRIX, "_ATTRIBUTION_BY_VERDICT")
        | _returns_of_functions_named_like(MATRIX_POLICY)
        | _returns_of_functions_named_like(BUILD_MATRIX)
        | _dict_key_writes()
    )


def glossary() -> set[str]:
    text = TONEMAP.read_text(encoding="utf-8")
    _, _, rest = text.partition("MATRIX_ATTRIBUTION_CN: Record<string, string> = {")
    assert rest, "MATRIX_ATTRIBUTION_CN not found in ui/toneMap.ts — probe broken"
    body, _, _ = rest.partition("\n};")
    keys = set(_KEY_RE.findall(body))
    assert keys, "MATRIX_ATTRIBUTION_CN parsed empty — probe broken"
    return keys


def test_the_probe_reads_a_real_vocabulary() -> None:
    produced = domain()
    assert {"head", "base", "not_attributed", "none", "unknown"} <= produced, (
        f"the row attribution vocabulary shrank to {sorted(produced)}: one of the "
        "three producer shapes (verdict table / function return / direct key write) "
        "is no longer being read, and a silent narrowing here would make the "
        "comparison below meaningless"
    )


def test_the_attribution_glossary_equals_the_produced_domain() -> None:
    produced, named = domain(), glossary()
    assert named == produced, (
        f"words with no value: {sorted(named - produced)}; attributions a reviewer "
        f"would see in raw English: {sorted(produced - named)}"
    )


def test_head_and_base_never_share_a_meaning() -> None:
    """The distinction a reviewer acts on: this change vs a pre-existing one."""
    table = _table_values(BUILD_MATRIX, "_ATTRIBUTION_BY_VERDICT")
    assert {"head", "base"} <= table
    text = TONEMAP.read_text(encoding="utf-8")
    head = next((raw for raw in text.splitlines() if raw.strip().startswith('head: "')), "")
    base = next((raw for raw in text.splitlines() if raw.strip().startswith('base: "')), "")
    assert "本次变更" in head and "改前" in base, (
        f"head={head!r} base={base!r} — the two must not read as the same thing"
    )
