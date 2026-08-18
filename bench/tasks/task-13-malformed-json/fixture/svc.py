# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Payload parsing (task-13)."""

import json


def parse_payload(raw: str) -> dict:
    return json.loads(raw)
