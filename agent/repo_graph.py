"""Repository symbol graph — call-graph-augmented retrieval (P2 RAG core).

The innovation: instead of depending on an external embedding service for
semantic retrieval, SpecProof builds a DETERMINISTIC symbol graph of the
repository (classes, methods, call sites) and uses it to EXPAND keyword
retrieval hits into their semantic neighborhood (callees, callers,
same-class siblings). A hit on "changeEmail" then carries the context of
UserService writes, the repository calls and the event publisher — exactly
what a verifier needs, without any model in the loop.

Graph format:
    methods:       method FQN -> owning class FQN
    method_calls:  method FQN -> set of called simple names
"""

from __future__ import annotations

import re
from typing import Any

from agent.checkers.java_source import _split_with_annotations

_CLASS_RE = re.compile(
    r"(?:public\s+)?(?:final\s+)?(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)"
)
_PKG_RE = re.compile(r"^package\s+([\w.]+);", re.M)
_CALL_RE = re.compile(r"[\w.]*?(\w+)\s*\(")


class RepoGraph:
    """Deterministic symbol graph over a repository snapshot."""

    def __init__(self, files: dict[str, str]) -> None:
        self.files = files
        self.methods: dict[str, str] = {}          # method FQN -> class FQN
        self.class_files: dict[str, str] = {}      # class FQN -> file path
        self.method_calls: dict[str, set[str]] = {}  # method FQN -> called names
        self._build()

    def _build(self) -> None:
        for path, content in self.files.items():
            if not path.endswith(".java"):
                continue
            pkg_match = _PKG_RE.search(content)
            pkg = pkg_match.group(1) if pkg_match else ""
            classes = _CLASS_RE.findall(content)
            owner_fqn = (
                (pkg + "." + classes[0]) if (pkg and classes)
                else (classes[0] if classes else path)
            )
            for cls in classes:
                fqn = (pkg + "." + cls) if pkg else cls
                self.class_files.setdefault(fqn, path)
            for block, name in _split_with_annotations(content):
                method_fqn = owner_fqn + "." + name
                self.methods[method_fqn] = owner_fqn
                self.method_calls[method_fqn] = set(_CALL_RE.findall(block))

    def symbols(self) -> list[str]:
        return sorted(self.methods)

    def resolve(self, simple_name: str) -> list[str]:
        """All method FQNs whose name matches (exact or suffix)."""
        return [m for m in self.methods if m.endswith("." + simple_name)]

    def neighbors(self, symbol: str, hops: int = 1) -> list[str]:
        """Semantic neighborhood: callees, callers, same-class siblings."""
        if symbol not in self.methods:
            return []
        owner = self.methods[symbol]
        seen: set[str] = {symbol}
        frontier = {symbol}
        for _ in range(hops):
            nxt: set[str] = set()
            for s in frontier:
                # 1) callees of s
                for callee in self.method_calls.get(s, set()):
                    nxt.update(self.resolve(callee))
                # 2) callers of s
                for m, calls in self.method_calls.items():
                    if (
                        s.endswith("." + next(iter(self.resolve(s)), s.rsplit(".", 1)[-1]))
                        or s in calls
                    ):
                        nxt.add(m)
                    if any(c == s.rsplit(".", 1)[-1] for c in calls):
                        nxt.add(m)
                # 3) siblings in the same class
                for m, o in self.methods.items():
                    if o == owner and m != s:
                        nxt.add(m)
            for s2 in nxt:
                if s2 not in seen:
                    seen.add(s2)
            frontier = {s2 for s2 in nxt if s2 not in seen}
            if not frontier:
                break
        return sorted(seen - {symbol})

    def expand_hits(
        self, hits: list[dict[str, Any]], hops: int = 1,
    ) -> list[dict[str, Any]]:
        """Expand retrieval hits with their graph neighborhood.

        Each hit contributes its own symbol plus its neighbors (deduped),
        so the contract compiler sees the surrounding call context.
        """
        expanded: dict[str, dict[str, Any]] = {}
        for h in hits:
            symbol = h.get("symbol", "")
            if not symbol:
                continue
            key = h.get("path", "") + "::" + symbol
            expanded.setdefault(key, h)
            # The symbol in ES is the method simple name; resolve it.
            resolved = self.resolve(symbol) or [symbol]
            for r in resolved:
                for nb in self.neighbors(r, hops):
                    nb_simple = nb.rsplit(".", 1)[-1]
                    for nb_hit in self._symbol_docs(nb):
                        nk = nb_hit.get("path", "") + "::" + nb_hit.get("symbol", nb_simple)
                        expanded.setdefault(nk, nb_hit)
        return list(expanded.values())

    def _symbol_docs(self, method_fqn: str) -> list[dict[str, Any]]:
        """Reconstruct a doc-like entry for a graph symbol."""
        owner = self.methods.get(method_fqn, "")
        file_path = self.class_files.get(owner, "")
        simple = method_fqn.rsplit(".", 1)[-1]
        content = ""
        if file_path and file_path in self.files:
            for block, name in _split_with_annotations(self.files[file_path]):
                if name == simple:
                    content = block[:800]
                    break
        return [{
            "path": file_path,
            "symbol": simple,
            "content": content,
            "source": "symbol_graph",
        }]
