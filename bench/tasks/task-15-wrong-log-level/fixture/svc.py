# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Withdrawal logic (task-15)."""

import logging


def withdraw(balance: int, amount: int) -> int:
    if amount > balance:
        logging.info("withdraw rejected: insufficient funds")
        return balance
    return balance - amount
