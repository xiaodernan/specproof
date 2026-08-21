"""devtools.archreview — deterministic architecture review (DevMind port).

Builds the internal import graph of a Python project from stdlib ast and
reports structural findings: circular imports, dependency metrics
(hubs, orphans) and optional layer-rule violations.

Honesty contract:
- cycles are real cycles in the import graph, reported with the module
  list, never guessed;
- layer rules fire only when the caller supplies layer definitions
  (regex -> layer name) and allowed edges — no rules, no fabricated
  violations;
- third-party imports are classified by the stdlib allowlist heuristic
  and reported as "external" without claiming accuracy about packaging.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

from devtools.quality import collect_python_files

_STDLIB = set(sys.stdlib_module_names)


def _module_name(rel: str) -> str:
    """posix rel path -> dotted module name ('' for __init__ siblings)."""
    parts = rel[:-3].split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(p for p in parts if p)


def _imports_of(tree: ast.Module) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def build_graph(root: Path) -> dict[str, Any]:
    """Module names -> {internal imports, external imports}."""
    files = collect_python_files(root)
    modules: set[str] = set()
    for path in files:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        name = _module_name(rel)
        if name:
            modules.add(name)
    graph: dict[str, dict[str, list[str]]] = {}
    for path in files:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        name = _module_name(rel)
        if not name:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            graph[name] = {"internal": [], "external": []}
            continue
        internal: list[str] = []
        external: list[str] = []
        for imp in _imports_of(tree):
            top = imp.split(".")[0]
            hit: str | None = None
            if top not in _STDLIB:
                parts = imp.split(".")
                for i in range(len(parts), 0, -1):
                    prefix = ".".join(parts[:i])
                    if prefix in modules:
                        hit = prefix
                        break
            if hit is not None:
                if hit != name and hit not in internal:
                    internal.append(hit)
            elif top not in _STDLIB and imp not in external:
                external.append(imp)
        graph[name] = {"internal": internal, "external": external}
    return {"modules": sorted(modules), "graph": graph}


def _find_cycles(graph: dict[str, dict[str, list[str]]]) -> list[list[str]]:
    """DFS cycle detection over internal edges (deduped, deterministic)."""
    edges: set[tuple[str, str]] = set()
    for src, data in graph.items():
        for dst in data["internal"]:
            edges.add((src, dst))
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    for start_node in sorted({s for (s, _d) in edges}):
        stack: list[tuple[str, list[str]]] = [(start_node, [start_node])]
        while stack:
            node, path = stack.pop()
            for nxt in sorted(d for (s, d) in edges if s == node):
                if nxt == start_node and len(path) > 1:
                    key = frozenset(path)
                    if key not in seen:
                        seen.add(key)
                        cycles.append(path + [nxt])
                elif nxt not in path and len(path) < 16:
                    stack.append((nxt, path + [nxt]))
    return cycles


def _layer_of(module: str, rules: dict[str, str]) -> str | None:
    for pattern, layer in rules.items():
        if re.search(pattern, module):
            return layer
    return None


def review(
    root: Path,
    layer_rules: dict[str, str] | None = None,
    allowed_edges: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the graph and report findings. Layer rules are optional and
    never invented — without them no layering violations are reported."""
    built = build_graph(root)
    graph: dict[str, dict[str, list[str]]] = built["graph"]
    modules: list[str] = built["modules"]
    cycles = _find_cycles(graph)
    findings: list[dict[str, Any]] = []
    for cycle in cycles:
        findings.append({
            "type": "architecture",
            "subtype": "circular_import",
            "severity": "high",
            "modules": cycle,
            "message": "circular import: " + " -> ".join(cycle + cycle[:1]),
            "suggestion": "break the cycle via dependency inversion",
        })
    if layer_rules:
        allowed = set(allowed_edges or [])
        for src, data in graph.items():
            src_layer = _layer_of(src, layer_rules)
            if src_layer is None:
                continue
            for dst in data["internal"]:
                dst_layer = _layer_of(dst, layer_rules)
                if dst_layer is None:
                    continue
                if (src_layer, dst_layer) in allowed:
                    continue
                findings.append({
                    "type": "architecture",
                    "subtype": "layer_violation",
                    "severity": "medium",
                    "file": src,
                    "imports": dst,
                    "message": (
                        src + " (" + src_layer + ") imports " + dst + " ("
                        + dst_layer + ") — not an allowed edge"
                    ),
                    "suggestion": (
                        "route through an allowed layer or reconsider "
                        "the edge"
                    ),
                })
    indegree: dict[str, int] = dict.fromkeys(modules, 0)
    for data in graph.values():
        for dst in data["internal"]:
            indegree[dst] = indegree.get(dst, 0) + 1
    hubs = sorted(
        [m for m in modules if indegree.get(m, 0) >= 5],
        key=lambda m: (-indegree.get(m, 0), m),
    )[:10]
    orphans = sorted(
        m for m in modules
        if not graph[m]["internal"] and indegree.get(m, 0) == 0
        and m != "__main__"
    )
    return {
        "root": str(root),
        "module_count": len(modules),
        "edge_count": sum(len(d["internal"]) for d in graph.values()),
        "cycles": cycles,
        "findings": findings,
        "hubs": [
            {"module": m, "imported_by": indegree.get(m, 0)} for m in hubs
        ],
        "orphans": orphans,
    }
