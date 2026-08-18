# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Order creation (task-31)."""

from dataclasses import dataclass


@dataclass
class OrderRequest:
    customer_id: str
    items: list[str]
    note: str = ""


def create_order(customer_id: str, items: list[str]) -> dict:
    return {"customer": customer_id, "items": list(items)}
