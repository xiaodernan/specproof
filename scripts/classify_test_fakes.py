"""Classify the hand-written fakes in the test suite: SQL fake or not?

The ledger's queue item said "replace the remaining hand-written fakes
with an evaluator" — and then measured that the framing was WRONG: most
of those fakes are not SQL fakes at all, they are method-level duck
types (they implement the repository's methods, not a SQL surface). A
query evaluator can replace the first kind; replacing the second kind
with one would turn it into a real store, which is a different kind of
change entirely.

This script makes that distinction countable and repeatable, so the
queue item can be re-framed from measurements instead of from a hunch.

Usage:
    python scripts/classify_test_fakes.py            # the report
    python scripts/classify_test_fakes.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"

#: The surface a QUERY EVALUATOR could stand in for: it speaks SQL.
SQL_SURFACE = frozenset({
    "execute", "executemany", "fetchone", "fetchall", "fetchmany",
    "cursor", "commit", "rollback", "query", "select", "insert", "update",
})

#: The surface of a STORE/REPOSITORY double: it speaks the domain's
#: methods. A query evaluator is NOT a drop-in for these.
STORE_SURFACE = frozenset({
    "save", "save_and_flush", "find", "find_by_id", "find_all", "find_one",
    "get", "set", "delete", "update", "list", "iter", "scan", "publish",
    "xadd", "lpush", "rpush", "incr", "expire", "enqueue", "dequeue",
    "claim", "ack", "nack", "heartbeat", "renew", "put", "fetch",
})


@dataclass
class FakeClass:
    path: str
    line: int
    name: str
    methods: list[str] = field(default_factory=list)

    @property
    def sql_surface(self) -> list[str]:
        return [m for m in self.methods if m in SQL_SURFACE]

    @property
    def store_surface(self) -> list[str]:
        return [m for m in self.methods if m in STORE_SURFACE]

    @property
    def kind(self) -> str:
        if self.sql_surface:
            return "sql-fake"
        if self.store_surface:
            return "store-duck-type"
        return "plain-double"


def _is_fake_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(("fake", "stub", "mock", "dummy"))
        or lowered.endswith(("fake", "stub", "mock", "double", "store", "db"))
        or "fake" in lowered
    )


def _classes(path: Path) -> list[FakeClass]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    found: list[FakeClass] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_fake_name(node.name):
            continue
        methods = [
            item.name for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        found.append(FakeClass(
            path=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            line=node.lineno,
            name=node.name,
            methods=methods,
        ))
    return found


def collect() -> list[FakeClass]:
    everything: list[FakeClass] = []
    for path in sorted(TESTS.rglob("*.py")):
        everything.extend(_classes(path))
    return everything


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    args = parser.parse_args(argv)

    fakes = collect()
    buckets: dict[str, list[FakeClass]] = {
        "sql-fake": [], "store-duck-type": [], "plain-double": [],
    }
    for fake in fakes:
        buckets[fake.kind].append(fake)

    if args.json:
        print(json.dumps({
            "total": len(fakes),
            "counts": {k: len(v) for k, v in buckets.items()},
            "sql_fakes": [
                {
                    "path": f.path, "line": f.line, "name": f.name,
                    "sql_methods": f.sql_surface,
                }
                for f in buckets["sql-fake"]
            ],
        }, indent=2, ensure_ascii=False))
        return 0

    print(f"Hand-written fakes in tests/: {len(fakes)}\n")
    for kind, items in buckets.items():
        print(f"  {kind:18s} {len(items)}")
    print()
    print("The SQL fakes — the only ones a query evaluator could stand in for:")
    for fake in buckets["sql-fake"]:
        print(f"    {fake.path}:{fake.line} {fake.name}"
              f"  [{', '.join(fake.sql_surface)}]")
    print()
    print("The store duck types — an evaluator is NOT a drop-in for these:")
    for fake in buckets["store-duck-type"]:
        print(f"    {fake.path}:{fake.line} {fake.name}"
              f"  [{', '.join(fake.store_surface[:6])}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
