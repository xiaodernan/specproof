"""Repository Digital Twin — first slice (计划书 §19.4).

A queryable, in-memory twin of a repository built from the symbol index
(retrieval/symbols.py RepoIndex): modules, module-level dependency edges,
API surface, migrations, owners and deterministic risk scores. Everything
is pure data plus two pure functions; nothing touches the network, the
disk or any live service.

Honest scope (first slice):

- Module granularity is path-derived (top-level segment, with common
  container roots extended one level); semantic module detection is a
  later slice.
- Dependency edges come from cross-module call/ref edges in the symbol
  index. Conservative regex parsers (TypeScript/Go/Java) may under- or
  over-count those edges, so graph distance is an estimate, never a proof.
- Migrations are detected by path segments (migration/migrate) only;
  schema-aware migration parsing is a later slice.
- Owners come from an explicit mapping, a CODEOWNERS file present in the
  index, or a derived area fallback (deepest path segment).
- Risk scores are a documented, deterministic combination of dependency
  coupling, migration presence and conservative-parser uncertainty.
"""

from __future__ import annotations

import fnmatch
import re
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

from retrieval.symbols import RepoIndex, Symbol

# A file belongs to its top-level path segment, except that common
# container roots are extended with the next segment (src/orders, not src).
_COMMON_ROOTS: frozenset[str] = frozenset(
    {"src", "lib", "app", "packages", "pkg", "services"}
)

# Files that describe ownership rather than code; they never form modules.
_OWNER_FILE_NAMES: frozenset[str] = frozenset({"codeowners", "owners"})

#: Migration files are recognized by a migrations/migrate path segment.
_MIGRATION_PATH_RE: re.Pattern[str] = re.compile(
    r"(^|/)(migrations?|migrate)(/|$)", re.IGNORECASE
)

#: Risk model weights (deterministic, documented in the module docstring).
_RISK_DEPENDENCY_WEIGHT = 0.5
_RISK_MIGRATION_WEIGHT = 0.3
_RISK_UNCERTAINTY_WEIGHT = 0.2
_DEPENDENCY_DIVISOR = 20.0


@dataclass(frozen=True)
class TwinModule:
    """One module of the twin: name, member paths and symbol accounting."""

    name: str
    paths: tuple[str, ...]
    symbol_count: int
    conservative_count: int


@dataclass(frozen=True)
class DependencyEdge:
    """A module-level dependency derived from a cross-module symbol edge."""

    source: str
    target: str
    via: str


@dataclass(frozen=True)
class ApiEntry:
    """A boundary symbol of a module (cross-module referenced or public)."""

    module: str
    path: str
    symbol: str
    kind: str
    line: int


@dataclass(frozen=True)
class MigrationEntry:
    """A migration file and the module that owns it."""

    module: str
    path: str


@dataclass(frozen=True)
class ImpactEntry:
    """One impacted module of an impact estimate."""

    module: str
    distance: int
    reason: str
    risk_score: float


@dataclass(frozen=True)
class RepositoryTwin:
    """In-memory repository twin (计划书 §19.4 first slice)."""

    modules: dict[str, TwinModule]
    dependencies: tuple[DependencyEdge, ...]
    apis: tuple[ApiEntry, ...]
    migrations: tuple[MigrationEntry, ...]
    owners: dict[str, str]
    risk_scores: dict[str, float]


def _module_of_path(path: str) -> str:
    normalized = path.replace("\\", "/").lstrip("./")
    segments = [segment for segment in normalized.split("/") if segment]
    if not segments:
        return ""
    if segments[0].lower() in _COMMON_ROOTS and len(segments) > 1:
        return f"{segments[0]}/{segments[1]}"
    return segments[0]


def _is_migration_path(path: str) -> bool:
    return _MIGRATION_PATH_RE.search(path.replace("\\", "/")) is not None


def _derived_area_owner(module: str) -> str:
    """Deepest path segment — a placeholder owner until real data exists."""
    return module.split("/")[-1]


def _owners_from_codeowners(content: str, modules: Iterable[str]) -> dict[str, str]:
    """Parse a CODEOWNERS file; the last matching pattern wins (git semantics).

    First-slice semantics: patterns match module names with fnmatch
    wildcards; git directory-recursion semantics are a later slice.
    """
    patterns: list[tuple[str, str]] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        pattern = parts[0].lstrip("/")
        owners = ", ".join(part.lstrip("@") for part in parts[1:])
        patterns.append((pattern, owners))
    result: dict[str, str] = {}
    for module in modules:
        owner = ""
        for pattern, candidate in patterns:
            if fnmatch.fnmatchcase(module, pattern):
                owner = candidate
        result[module] = owner or _derived_area_owner(module)
    return result


def build_from_symbol_index(
    index: RepoIndex,
    *,
    owners: Mapping[str, str] | None = None,
) -> RepositoryTwin:
    """Build the twin from an in-memory RepoIndex (pure; no I/O)."""
    module_paths: dict[str, list[str]] = {}
    file_modules: dict[str, str] = {}
    for path in index.files:
        if Path(path).name.lower() in _OWNER_FILE_NAMES:
            continue
        module = _module_of_path(path)
        if not module:
            continue
        file_modules[path] = module
        module_paths.setdefault(module, []).append(path)

    by_id: dict[str, Symbol] = {symbol.symbol_id: symbol for symbol in index.symbols}
    by_name: dict[str, list[Symbol]] = {}
    symbols_by_module: dict[str, list[Symbol]] = {}
    conservative: dict[str, int] = {}
    for symbol in index.symbols:
        by_name.setdefault(symbol.name, []).append(symbol)
        symbol_module = file_modules.get(symbol.file)
        if symbol_module is None:
            continue
        symbols_by_module.setdefault(symbol_module, []).append(symbol)
        if symbol.conservative:
            conservative[symbol_module] = conservative.get(symbol_module, 0) + 1

    edges: set[tuple[str, str, str]] = set()
    boundary_symbol_ids: set[str] = set()
    for caller_id, referenced_name in chain(index.calls, index.refs):
        caller = by_id.get(caller_id)
        if caller is None:
            continue
        source = file_modules.get(caller.file)
        if source is None:
            continue
        for candidate in by_name.get(referenced_name, []):
            target_module = file_modules.get(candidate.file)
            if target_module is None or target_module == source:
                continue
            edges.add((source, target_module, referenced_name))
            boundary_symbol_ids.add(candidate.symbol_id)

    apis: dict[tuple[str, str, int, str, str], ApiEntry] = {}
    for symbol_id in boundary_symbol_ids:
        symbol = by_id[symbol_id]
        module = file_modules[symbol.file]
        key = (module, symbol.file, symbol.line, symbol.name, symbol.kind)
        apis.setdefault(
            key,
            ApiEntry(
                module=module,
                path=symbol.file,
                symbol=symbol.name,
                kind=symbol.kind,
                line=symbol.line,
            ),
        )
    for module, symbols in symbols_by_module.items():
        if any(entry.module == module for entry in apis.values()):
            continue
        for symbol in sorted(symbols, key=lambda s: (s.file, s.line, s.name)):
            if symbol.kind not in {"class", "interface", "function"}:
                continue
            if symbol.name.startswith("_"):
                continue
            apis[(module, symbol.file, symbol.line, symbol.name, symbol.kind)] = (
                ApiEntry(
                    module=module,
                    path=symbol.file,
                    symbol=symbol.name,
                    kind=symbol.kind,
                    line=symbol.line,
                )
            )

    migrations = sorted(
        (
            MigrationEntry(module=module, path=path)
            for path, module in file_modules.items()
            if _is_migration_path(path)
        ),
        key=lambda entry: (entry.module, entry.path),
    )
    dependencies = tuple(
        DependencyEdge(source, target, via) for source, target, via in sorted(edges)
    )
    apis_sorted = tuple(
        sorted(
            apis.values(),
            key=lambda entry: (entry.module, entry.path, entry.line, entry.symbol),
        )
    )

    fan_in: dict[str, int] = {}
    fan_out: dict[str, int] = {}
    for source, target, _via in edges:
        fan_out[source] = fan_out.get(source, 0) + 1
        fan_in[target] = fan_in.get(target, 0) + 1
    migration_modules = {migration.module for migration in migrations}
    risk_scores: dict[str, float] = {}
    for module in sorted(module_paths):
        total = len(symbols_by_module.get(module, []))
        dependency_factor = min(
            1.0, (fan_in.get(module, 0) + fan_out.get(module, 0)) / _DEPENDENCY_DIVISOR
        )
        migration_factor = 1.0 if module in migration_modules else 0.0
        uncertainty_factor = conservative.get(module, 0) / max(1, total)
        risk_scores[module] = round(
            _RISK_DEPENDENCY_WEIGHT * dependency_factor
            + _RISK_MIGRATION_WEIGHT * migration_factor
            + _RISK_UNCERTAINTY_WEIGHT * uncertainty_factor,
            4,
        )

    if owners is not None:
        owner_map = {
            module: owners.get(module, _derived_area_owner(module))
            for module in sorted(module_paths)
        }
    else:
        codeowners = index.files.get("CODEOWNERS") or index.files.get(
            ".github/CODEOWNERS"
        )
        if codeowners is not None:
            owner_map = _owners_from_codeowners(codeowners, sorted(module_paths))
        else:
            owner_map = {
                module: _derived_area_owner(module) for module in sorted(module_paths)
            }

    modules = {
        module: TwinModule(
            name=module,
            paths=tuple(sorted(paths)),
            symbol_count=len(symbols_by_module.get(module, [])),
            conservative_count=conservative.get(module, 0),
        )
        for module, paths in sorted(module_paths.items())
    }
    return RepositoryTwin(
        modules=modules,
        dependencies=dependencies,
        apis=apis_sorted,
        migrations=tuple(migrations),
        owners=owner_map,
        risk_scores=risk_scores,
    )


def impact_estimate(
    twin: RepositoryTwin,
    changed_paths: Iterable[str],
) -> list[ImpactEntry]:
    """Estimate affected modules for changed paths, sorted by graph distance.

    Distance is counted over dependents edges (modules that consume the
    changed module), so a change propagates downstream to consumers only.
    Changed paths that do not belong to any twin module are ignored.
    Ties inside one distance ring are ordered by descending risk score,
    then by module name — deterministic for stable reporting.
    """
    dependents: dict[str, set[str]] = {}
    for edge in twin.dependencies:
        dependents.setdefault(edge.target, set()).add(edge.source)

    changed_modules: dict[str, str] = {}
    for path in changed_paths:
        module = _module_of_path(path)
        if module in twin.modules and module not in changed_modules:
            changed_modules[module] = path

    entries: dict[str, ImpactEntry] = {
        module: ImpactEntry(
            module=module,
            distance=0,
            reason=f"changed: {path}",
            risk_score=twin.risk_scores.get(module, 0.0),
        )
        for module, path in changed_modules.items()
    }
    frontier: deque[str] = deque(changed_modules)
    distance = 0
    while frontier:
        distance += 1
        next_frontier: list[str] = []
        for module in frontier:
            for dependent in sorted(dependents.get(module, ())):
                if dependent in entries:
                    continue
                entries[dependent] = ImpactEntry(
                    module=dependent,
                    distance=distance,
                    reason=f"depends on {module}",
                    risk_score=twin.risk_scores.get(dependent, 0.0),
                )
                next_frontier.append(dependent)
        frontier = deque(next_frontier)
    return sorted(
        entries.values(),
        key=lambda entry: (entry.distance, -entry.risk_score, entry.module),
    )


__all__ = [
    "ApiEntry",
    "DependencyEdge",
    "ImpactEntry",
    "MigrationEntry",
    "RepositoryTwin",
    "TwinModule",
    "build_from_symbol_index",
    "impact_estimate",
]
