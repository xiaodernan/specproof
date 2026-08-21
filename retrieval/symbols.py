"""Minimal four-language symbol indexer (SpecCraft 计划书 §22-5 / M2).

Python symbols come from the stdlib ``ast`` module (exact, with scoped
references). TypeScript and Go are extracted with conservative regexes —
no tree-sitter dependency — and every symbol is flagged ``conservative``.
Java reuses the repo_graph / ``_split_with_annotations`` splitting style
(equivalent pattern family + brace matching) so the M2 index stays
equivalent to the existing P2 call graph for Java corpora.

The index is deliberately in-memory: the 30-query retrieval benchmark
(scripts/bench_retrieval.py) consumes ``RepoIndex`` directly; nothing is
written to Elasticsearch here (storage/elasticsearch.py stays untouched).

Honesty contract (卷IV 4.3): a file that cannot be read or parsed never
aborts the run — it is recorded in ``IndexStats.errors`` / ``notes``.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

LANGUAGE_EXTS: dict[str, tuple[str, ...]] = {
    "python": (".py",),
    "typescript": (".ts", ".tsx"),
    "java": (".java",),
    "go": (".go",),
}

DEFAULT_EXCLUSIONS: tuple[str, ...] = (
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "target",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "site-packages",
)

# Call-site tokens that are language keywords / primitives, not symbols.
_NON_SYMBOL_TOKENS: frozenset[str] = frozenset({
    "if", "for", "while", "switch", "catch", "return", "new", "throw",
    "assert", "import", "package", "func", "type", "var", "const", "range",
    "go", "defer", "map", "make", "len", "cap", "append", "delete",
    "select", "chan", "case", "default", "else", "break", "continue",
    "goto", "interface", "struct", "class", "extends", "implements",
    "super", "this", "typeof", "instanceof", "in", "of", "await",
    "async", "yield", "try", "finally", "null", "true", "false", "void",
    "int", "long", "double", "float", "boolean", "byte", "char", "short",
    "string", "public", "private", "protected", "static", "final",
    "synchronized", "volatile", "transient", "native", "abstract", "do",
})

_IDENT_TS = r"[A-Za-z_$][\w$]*"
_IDENT = r"\w+"

# TypeScript — conservative regexes (no AST precision, by design).
_TS_FUNCTION_RE: re.Pattern[str] = re.compile(
    rf"(?m)(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+({_IDENT_TS})"
)
_TS_ARROW_RE: re.Pattern[str] = re.compile(
    rf"(?m)(?:export\s+)?(?:const|let|var)\s+({_IDENT_TS})\s*=\s*"
    rf"(?:async\s*)?(?:\([^)]*\)|{_IDENT_TS})\s*=>"
)
_TS_CLASS_RE: re.Pattern[str] = re.compile(
    rf"(?m)(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+({_IDENT_TS})"
)
_TS_INTERFACE_RE: re.Pattern[str] = re.compile(
    rf"(?m)(?:export\s+)?interface\s+({_IDENT_TS})"
)
_TS_IMPORT_RE: re.Pattern[str] = re.compile(
    r'''(?m)^\s*import\s+(?:type\s+)?(?:[^'"]*?from\s+)?['"]([^'"]+)['"]\s*;?'''
)
_TS_EXPORT_NAMED_RE: re.Pattern[str] = re.compile(r"(?m)export\s+\{([^}]*)}")
# Declaration guard: reject IDENT( that closes with ") {" (method/function
# declarations inside scanned bodies), keep real call sites.
_TS_CALL_RE: re.Pattern[str] = re.compile(
    rf"(?<![.\w$])({_IDENT_TS})\s*\((?!\s*[^)]*\)\s*{{)"
)

# Go — conservative regexes.
_GO_FUNC_RE: re.Pattern[str] = re.compile(
    rf"(?m)^func\s+(?:\((\w+)\s+\*?\w+\)\s+)?({_IDENT})\s*\("
)
_GO_TYPE_RE: re.Pattern[str] = re.compile(
    rf"(?m)^type\s+({_IDENT})\s+(?:struct|interface)\b"
)
_GO_IMPORT_SINGLE_RE: re.Pattern[str] = re.compile(
    r'(?m)^import\s+(?:(\w+)\s+)?[`"]([^`"]+)[`"]'
)
_GO_IMPORT_BLOCK_RE: re.Pattern[str] = re.compile(
    r"(?ms)^import\s*\(\s*(.*?)\s*\)"
)
_GO_IMPORT_ITEM_RE: re.Pattern[str] = re.compile(
    r'(?m)(?:(\w+)\s+)?[`"]([^`"]+)[`"]'
)
_GO_CALL_RE: re.Pattern[str] = re.compile(rf"\b({_IDENT})\s*\(")

# Java — equivalent of agent/checkers/java_source._SPLIT_RE (repo_graph
# style): annotations (one nested-paren level) + modifiers + return type +
# name + params + optional throws + opening brace, then brace matching.
_JAVA_TYPE_RE: re.Pattern[str] = re.compile(
    rf"(?m)(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?"
    rf"(?:abstract\s+)?(?:class|interface|enum|record)\s+({_IDENT})"
)
_JAVA_METHOD_RE: re.Pattern[str] = re.compile(
    rf"(?:(?:@\w+(?:\([^()]*(?:\([^()]*\))?[^()]*\))?\s*)*)"
    rf"(?:public|private|protected|static|final|default|\s)+"
    rf"[\w<>,\[\]\s]+\s+({_IDENT})\s*\([^)]*\)\s*(?:throws[^{{]+)?\{{"
)
_JAVA_IMPORT_RE: re.Pattern[str] = re.compile(r"(?m)^import\s+(?:static\s+)?([\w.]+);")
_JAVA_CALL_RE: re.Pattern[str] = re.compile(r"[\w.]*?(\w+)\s*\(")

# ---------------------------------------------------------------------------
# data model
# ---------------------------------------------------------------------------


@dataclass
class Symbol:
    """One extracted symbol (function/class/method/import/... with refs)."""

    name: str
    kind: str
    file: str
    line: int
    end_line: int = 0
    refs: list[str] = field(default_factory=list)
    language: str = ""
    conservative: bool = False

    @property
    def symbol_id(self) -> str:
        """Stable edge endpoint: file:line:name."""
        return f"{self.file}:{self.line}:{self.name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "refs": list(self.refs),
            "language": self.language,
            "conservative": self.conservative,
        }


@dataclass
class ParseResult:
    """parse_* output: symbols plus honest notes and call edges.

    On a syntax error the symbols list is empty and the note explains why
    (conservative degradation, never a raised error).
    """

    symbols: list[Symbol]
    notes: list[str] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class IndexStats:
    files_scanned: int = 0
    files_ok: int = 0
    files_failed: int = 0
    symbol_count: int = 0
    symbols_by_language: dict[str, int] = field(default_factory=dict)
    symbols_by_kind: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_scanned": self.files_scanned,
            "files_ok": self.files_ok,
            "files_failed": self.files_failed,
            "symbol_count": self.symbol_count,
            "symbols_by_language": dict(self.symbols_by_language),
            "symbols_by_kind": dict(self.symbols_by_kind),
            "errors": list(self.errors),
            "notes": list(self.notes),
        }


@dataclass
class RepoIndex:
    """In-memory repository index: files + symbols + call/ref edges + stats."""

    files: dict[str, str]
    symbols: list[Symbol]
    calls: list[tuple[str, str]]
    refs: list[tuple[str, str]]
    stats: IndexStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbols": [s.to_dict() for s in self.symbols],
            "edges": {
                "calls": [list(edge) for edge in self.calls],
                "refs": [list(edge) for edge in self.refs],
            },
            "stats": self.stats.to_dict(),
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _match_brace(source: str, open_index: int) -> int:
    """Index just past the '}' that closes the brace at open_index.

    Mirrors the repo_graph splitter: no string/comment tracking — bodies
    containing braces inside literals are the documented approximation.
    """
    depth = 0
    i = open_index
    while i < len(source):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(source)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _call_refs(block: str, call_re: re.Pattern[str]) -> list[str]:
    return _unique(
        [token for token in call_re.findall(block) if token not in _NON_SYMBOL_TOKENS]
    )


def _py_expr_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _py_walk(
    node: ast.AST,
    scope: Symbol | None,
    calls: list[tuple[Symbol, str]],
) -> None:
    """Collect call targets + Load-name refs into the innermost symbol scope."""
    if isinstance(node, ast.Call):
        target = _py_expr_name(node.func)
        if target is not None and scope is not None:
            calls.append((scope, target))
            if target not in scope.refs:
                scope.refs.append(target)
    elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        if scope is not None and node.id not in scope.refs:
            scope.refs.append(node.id)
    for child in ast.iter_child_nodes(node):
        _py_walk(child, scope, calls)


# ---------------------------------------------------------------------------
# SymbolIndexer — the required entry point
# ---------------------------------------------------------------------------


class SymbolIndexer:
    """Four-language minimal symbol indexer (计划书 §22-5 / M2)."""

    _EXT_LANG: dict[str, str] = {
        ext: lang for lang, exts in LANGUAGE_EXTS.items() for ext in exts
    }

    # -- per-language parsers ------------------------------------------------

    @staticmethod
    def parse_python(source: str, file: str = "") -> ParseResult:
        """Parse Python with stdlib ast; syntax errors degrade to empty+note."""
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError) as exc:
            label = file or "<python>"
            return ParseResult(
                [],
                [f"{label}: syntax error: {exc} (line {getattr(exc, 'lineno', '?')})"],
            )

        symbols: list[Symbol] = []
        calls: list[tuple[Symbol, str]] = []

        def new_symbol(name: str, kind: str, node: ast.stmt) -> Symbol:
            sym = Symbol(
                name=name,
                kind=kind,
                file=file,
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                language="python",
            )
            symbols.append(sym)
            return sym

        def walk_body(body: list[ast.stmt], owner: Symbol | None) -> None:
            for stmt in body:
                if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                    kind = (
                        "method" if owner is not None and owner.kind == "class"
                        else "function"
                    )
                    sym = new_symbol(stmt.name, kind, stmt)
                    for decorator in stmt.decorator_list:
                        _py_walk(decorator, sym, calls)
                    for default in stmt.args.defaults:
                        _py_walk(default, sym, calls)
                    for kw_default in stmt.args.kw_defaults:
                        if kw_default is not None:
                            _py_walk(kw_default, sym, calls)
                    walk_body(stmt.body, sym)
                elif isinstance(stmt, ast.ClassDef):
                    sym = new_symbol(stmt.name, "class", stmt)
                    for base in stmt.bases:
                        _py_walk(base, sym, calls)
                    walk_body(stmt.body, sym)
                else:
                    _py_walk(stmt, owner, calls)
                    if owner is None:
                        if isinstance(stmt, ast.Assign):
                            for target in stmt.targets:
                                if isinstance(target, ast.Name):
                                    new_symbol(target.id, "assign", stmt)
                        elif isinstance(stmt, ast.AnnAssign) and isinstance(
                            stmt.target, ast.Name
                        ):
                            new_symbol(stmt.target.id, "assign", stmt)
                        elif isinstance(stmt, ast.Import | ast.ImportFrom):
                            for alias in stmt.names:
                                name = alias.asname or alias.name.split(".")[-1]
                                new_symbol(name, "import", stmt)

        walk_body(tree.body, None)
        return ParseResult(symbols, calls=[(s.symbol_id, t) for s, t in calls])

    @staticmethod
    def parse_typescript(source: str, file: str = "") -> ParseResult:
        """Conservative regex extraction for TypeScript (no tree-sitter)."""
        symbols: list[Symbol] = []
        calls: list[tuple[str, str]] = []

        def add(
            name: str, kind: str, line: int, end_line: int, refs: list[str],
        ) -> None:
            sym = Symbol(
                name=name,
                kind=kind,
                file=file,
                line=line,
                end_line=end_line,
                refs=refs,
                language="typescript",
                conservative=True,
            )
            symbols.append(sym)
            for ref in refs:
                calls.append((sym.symbol_id, ref))

        def body_refs(start: int, end: int) -> list[str]:
            if end <= start:
                return []
            return _call_refs(source[start:end], _TS_CALL_RE)

        for match in _TS_FUNCTION_RE.finditer(source):
            line = _line_of(source, match.start())
            end_line = line
            refs: list[str] = []
            brace = source.find("{", match.end())
            if brace != -1:
                end = _match_brace(source, brace)
                end_line = _line_of(source, end)
                refs = body_refs(match.end(), end)
            add(match.group(1), "function", line, end_line, refs)
        for match in _TS_ARROW_RE.finditer(source):
            line = _line_of(source, match.start())
            add(match.group(1), "function", line, line, [])
        for match in _TS_CLASS_RE.finditer(source):
            line = _line_of(source, match.start())
            end_line = line
            refs = []
            brace = source.find("{", match.end())
            if brace != -1:
                end = _match_brace(source, brace)
                end_line = _line_of(source, end)
                refs = body_refs(match.end(), end)
            add(match.group(1), "class", line, end_line, refs)
        for match in _TS_INTERFACE_RE.finditer(source):
            line = _line_of(source, match.start())
            end_line = line
            brace = source.find("{", match.end())
            if brace != -1:
                end_line = _line_of(source, _match_brace(source, brace))
            add(match.group(1), "interface", line, end_line, [])
        for match in _TS_IMPORT_RE.finditer(source):
            line = _line_of(source, match.start())
            add(match.group(1), "import", line, line, [])
        for match in _TS_EXPORT_NAMED_RE.finditer(source):
            line = _line_of(source, match.start())
            for raw_name in match.group(1).split(","):
                clean = raw_name.strip().split(" as ")[-1].strip()
                if clean:
                    add(clean, "export", line, line, [])
        note = (
            f"{file or '<typescript>'}: conservative regex extraction "
            "(no tree-sitter, no AST precision)"
        )
        return ParseResult(symbols, [note], calls)

    @staticmethod
    def parse_java(source: str, file: str = "") -> ParseResult:
        """repo_graph-style Java extraction (equivalent splitter regex)."""
        symbols: list[Symbol] = []
        calls: list[tuple[str, str]] = []
        for match in _JAVA_TYPE_RE.finditer(source):
            name = match.group(1)
            if name in _NON_SYMBOL_TOKENS:
                continue
            line = _line_of(source, match.start())
            end_line = line
            brace = source.find("{", match.end())
            if brace != -1:
                end_line = _line_of(source, _match_brace(source, brace))
            symbols.append(
                Symbol(name, "class", file, line, end_line, language="java")
            )
        for match in _JAVA_METHOD_RE.finditer(source):
            name = match.group(1)
            if name in _NON_SYMBOL_TOKENS:
                continue
            line = _line_of(source, match.start())
            end = _match_brace(source, match.end() - 1)
            end_line = _line_of(source, end)
            refs = _call_refs(source[match.end():end], _JAVA_CALL_RE)
            sym = Symbol(
                name, "method", file, line, end_line, refs=refs, language="java",
            )
            symbols.append(sym)
            for ref in refs:
                calls.append((sym.symbol_id, ref))
        for match in _JAVA_IMPORT_RE.finditer(source):
            line = _line_of(source, match.start())
            symbols.append(
                Symbol(match.group(1), "import", file, line, line, language="java")
            )
        return ParseResult(symbols, calls=calls)

    @staticmethod
    def parse_go(source: str, file: str = "") -> ParseResult:
        """Conservative regex extraction for Go (func/type/import)."""
        symbols: list[Symbol] = []
        calls: list[tuple[str, str]] = []
        for match in _GO_FUNC_RE.finditer(source):
            receiver = match.group(1)
            name = match.group(2)
            kind = "method" if receiver else "function"
            line = _line_of(source, match.start())
            end_line = line
            refs: list[str] = []
            brace = source.find("{", match.end())
            if brace != -1:
                end = _match_brace(source, brace)
                end_line = _line_of(source, end)
                refs = _call_refs(source[match.end():end], _GO_CALL_RE)
            sym = Symbol(name, kind, file, line, end_line, refs=refs, language="go")
            symbols.append(sym)
            for ref in refs:
                calls.append((sym.symbol_id, ref))
        for match in _GO_TYPE_RE.finditer(source):
            name = match.group(1)
            line = _line_of(source, match.start())
            end_line = line
            brace = source.find("{", match.end())
            if brace != -1:
                end_line = _line_of(source, _match_brace(source, brace))
            symbols.append(
                Symbol(name, "type", file, line, end_line, language="go")
            )
        for match in _GO_IMPORT_SINGLE_RE.finditer(source):
            line = _line_of(source, match.start())
            alias = match.group(1) or match.group(2)
            symbols.append(Symbol(alias, "import", file, line, line, language="go"))
        for block in _GO_IMPORT_BLOCK_RE.finditer(source):
            block_line = _line_of(source, block.start())
            for item in _GO_IMPORT_ITEM_RE.finditer(block.group(1)):
                alias = item.group(1) or item.group(2)
                symbols.append(
                    Symbol(alias, "import", file, block_line, block_line, language="go")
                )
        note = (
            f"{file or '<go>'}: conservative regex extraction "
            "(no go/parser dependency)"
        )
        return ParseResult(symbols, [note], calls)

    # -- repository indexing ---------------------------------------------------

    @classmethod
    def _parse(cls, file: str, source: str) -> ParseResult:
        ext = Path(file).suffix.lower()
        if ext == ".py":
            return cls.parse_python(source, file)
        if ext in (".ts", ".tsx"):
            return cls.parse_typescript(source, file)
        if ext == ".java":
            return cls.parse_java(source, file)
        if ext == ".go":
            return cls.parse_go(source, file)
        return ParseResult([])

    @classmethod
    def index_files(
        cls,
        files: dict[str, str],
        read_errors: list[str] | None = None,
    ) -> RepoIndex:
        """Index an in-memory {path: content} snapshot; per-file isolation."""
        symbols: list[Symbol] = []
        calls: list[tuple[str, str]] = []
        refs: list[tuple[str, str]] = []
        errors: list[str] = list(read_errors or [])
        notes: list[str] = []
        failed: set[str] = set()
        for path, content in files.items():
            try:
                result = cls._parse(path, content)
            except Exception as exc:  # noqa: BLE001 — per-file isolation
                errors.append(f"{path}: {type(exc).__name__}: {exc}")
                failed.add(path)
                continue
            notes.extend(result.notes)
            for sym in result.symbols:
                symbols.append(sym)
                for ref_name in sym.refs:
                    refs.append((sym.symbol_id, ref_name))
            calls.extend(result.calls)
        stats = IndexStats(
            files_scanned=len(files),
            files_ok=len(files) - len(failed),
            files_failed=len(failed),
            symbol_count=len(symbols),
            symbols_by_language=dict(Counter(s.language for s in symbols)),
            symbols_by_kind=dict(Counter(s.kind for s in symbols)),
            errors=errors,
            notes=notes,
        )
        return RepoIndex(
            files=dict(files),
            symbols=symbols,
            calls=calls,
            refs=refs,
            stats=stats,
        )

    @classmethod
    def index_repo(
        cls,
        repo_path: str | Path,
        exclusions: list[str] | tuple[str, ...] | None = None,
        include_dirs: list[str] | tuple[str, ...] | None = None,
    ) -> RepoIndex:
        """Walk repo_path and parse every supported source file.

        exclusions are directory/part names skipped anywhere in the path
        (defaults: .git, node_modules, venvs, caches, build outputs).
        include_dirs, when given, restricts files to those top-level dirs.
        """
        root = Path(repo_path)
        if root.is_file():
            text = root.read_text(encoding="utf-8", errors="replace")
            return cls.index_files({root.name: text})
        excluded = set(DEFAULT_EXCLUSIONS) | set(exclusions or ())
        included = tuple(include_dirs or ())
        files: dict[str, str] = {}
        read_errors: list[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            parts = rel.parts
            if any(part in excluded for part in parts[:-1]):
                continue
            if included and (not parts or parts[0] not in included):
                continue
            if path.suffix.lower() not in cls._EXT_LANG:
                continue
            try:
                files[rel.as_posix()] = path.read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError as exc:
                read_errors.append(f"{rel.as_posix()}: read failed: {exc}")
        return cls.index_files(files, read_errors)


def index_repo(
    repo_path: str | Path,
    exclusions: list[str] | tuple[str, ...] | None = None,
    include_dirs: list[str] | tuple[str, ...] | None = None,
) -> RepoIndex:
    """Module-level convenience wrapper around SymbolIndexer.index_repo."""
    return SymbolIndexer.index_repo(repo_path, exclusions, include_dirs)


# ---------------------------------------------------------------------------
# SymbolIndex — graph view for retrieval expansion
# ---------------------------------------------------------------------------


class SymbolIndex:
    """Graph view over a RepoIndex: resolve / neighbors / expand_hits / search.

    expand_hits mirrors agent.repo_graph.RepoGraph.expand_hits but is
    language-agnostic: edges come from the four-language extraction above
    (Java uses the same splitter style as RepoGraph, so behavior on Java
    corpora is equivalent).
    """

    def __init__(self, index: RepoIndex) -> None:
        self.index = index
        self._by_name: dict[str, list[Symbol]] = {}
        self._by_file: dict[str, list[Symbol]] = {}
        self._by_id: dict[str, Symbol] = {}
        self._callees: dict[str, list[str]] = {}
        self._callers: dict[str, list[str]] = {}
        self._refs_to: dict[str, list[str]] = {}
        self._lines: dict[str, list[str]] = {
            path: content.splitlines() for path, content in index.files.items()
        }
        for sym in index.symbols:
            self._by_name.setdefault(sym.name, []).append(sym)
            self._by_file.setdefault(sym.file, []).append(sym)
            self._by_id[sym.symbol_id] = sym
        for caller_id, callee in index.calls:
            self._callees.setdefault(caller_id, []).append(callee)
            self._callers.setdefault(callee, []).append(caller_id)
        for symbol_id, ref_name in index.refs:
            self._refs_to.setdefault(ref_name, []).append(symbol_id)

    def resolve(self, name: str) -> list[Symbol]:
        return list(self._by_name.get(name, []))

    def neighbors(self, sym: Symbol, hops: int = 1) -> list[str]:
        """Symbol ids of the neighborhood: callees/callers/refs/same-file."""
        start = sym.symbol_id
        seen: set[str] = {start}
        frontier = {start}
        for _ in range(max(1, hops)):
            nxt: set[str] = set()
            for sid in frontier:
                current = self._by_id.get(sid)
                if current is None:
                    continue
                for callee in self._callees.get(sid, []):
                    for target in self._by_name.get(callee, []):
                        nxt.add(target.symbol_id)
                for caller_id in self._callers.get(current.name, []):
                    nxt.add(caller_id)
                for ref_name in current.refs:
                    for target in self._by_name.get(ref_name, []):
                        nxt.add(target.symbol_id)
                for referrer_id in self._refs_to.get(current.name, []):
                    nxt.add(referrer_id)
                for sibling in self._by_file.get(current.file, []):
                    nxt.add(sibling.symbol_id)
            fresh = nxt - seen
            seen |= fresh
            frontier = fresh
            if not frontier:
                break
        return sorted(seen - {start})

    def _match(self, path: str, symbol_name: str) -> list[Symbol]:
        candidates = self._by_file.get(path, [])
        if symbol_name and symbol_name != path:
            named = [s for s in candidates if s.name == symbol_name]
            if named:
                return named
        return candidates

    def _symbol_doc(self, sym: Symbol) -> dict[str, Any]:
        content = ""
        lines = self._lines.get(sym.file)
        if lines is not None:
            start = max(0, sym.line - 1)
            end = min(len(lines), max(sym.end_line, sym.line) + 2)
            content = "\n".join(lines[start:end])[:800]
        return {
            "path": sym.file,
            "symbol": sym.name,
            "line": sym.line,
            "content": content,
            "language": sym.language,
            "source": "symbol_graph",
        }

    def expand_hits(
        self, hits: list[dict[str, Any]], hops: int = 1,
    ) -> list[dict[str, Any]]:
        """Append graph-neighborhood docs to retrieval hits (deduped)."""
        expanded: dict[tuple[str, str], dict[str, Any]] = {}
        for hit in hits:
            path = str(hit.get("path", ""))
            symbol_name = str(hit.get("symbol", ""))
            if not path:
                continue
            expanded.setdefault((path, symbol_name), dict(hit))
            for sym in self._match(path, symbol_name):
                for neighbor_id in self.neighbors(sym, hops):
                    neighbor = self._by_id.get(neighbor_id)
                    if neighbor is None:
                        continue
                    doc = self._symbol_doc(neighbor)
                    doc_key = (str(doc["path"]), str(doc["symbol"]))
                    expanded.setdefault(doc_key, doc)
        return list(expanded.values())

    def search(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Deterministic name/ref/kind lookup over indexed symbols."""
        tokens = _unique(re.findall(r"[A-Za-z_$][\w$]*|\d+", query))
        scored: list[tuple[float, Symbol]] = []
        for sym in self.index.symbols:
            score = 0.0
            for token in tokens:
                if sym.name == token:
                    score += 10.0
                elif token in sym.name:
                    score += 5.0
                if token in sym.refs:
                    score += 1.0
                if token == sym.kind:
                    score += 0.5
            if score > 0:
                scored.append((score, sym))
        scored.sort(
            key=lambda item: (-item[0], item[1].file, item[1].line, item[1].name)
        )
        out: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for score, sym in scored:
            key = (sym.file, sym.name)
            if key in seen:
                continue
            seen.add(key)
            doc = self._symbol_doc(sym)
            doc["score"] = score
            doc["source"] = "symbol_index"
            out.append(doc)
            if len(out) >= top_k:
                break
        return out


__all__ = [
    "DEFAULT_EXCLUSIONS",
    "IndexStats",
    "LANGUAGE_EXTS",
    "ParseResult",
    "RepoIndex",
    "Symbol",
    "SymbolIndex",
    "SymbolIndexer",
    "index_repo",
]
