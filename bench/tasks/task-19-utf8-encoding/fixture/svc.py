# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Text file reading (task-19)."""


def read_lines(path: str) -> list[str]:
    with open(path, encoding="ascii") as handle:
        return handle.read().splitlines()
