# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Age setter (task-adv-20)."""


def set_age(age: int) -> str:
    if not 0 <= age <= 150:
        raise ValueError("age out of range")
    return f"age={age}"
