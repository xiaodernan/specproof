# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""JSON serde (task-rec-09)."""

from datetime import datetime


def to_json_compatible(value: dict) -> dict:
    out = {}
    for key, item in value.items():
        out[key] = item.isoformat() if isinstance(item, datetime) else item
    return out


def from_json_compatible(value: dict) -> dict:
    raise NotImplementedError("phase 2 pending")
