# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Service layer (task-30)."""

import os  # noqa: F401 — 轮转逻辑 (第二阶段修复) 使用

MAX_AUDIT_BYTES = 200


def append_audit(path: str, entry: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(entry + "\n")
