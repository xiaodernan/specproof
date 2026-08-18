# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Weekend detection (task-34)."""

import time


def is_weekend() -> bool:
    return time.localtime().tm_wday >= 5
