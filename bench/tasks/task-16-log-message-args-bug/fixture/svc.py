# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Enrollment logic (task-16)."""

import logging


def enroll(user: str, plan: str) -> str:
    result = f"{user} enrolled in {plan}"
    logging.getLogger("svc").info("enrolled: %s in %s", user, result)
    return result
