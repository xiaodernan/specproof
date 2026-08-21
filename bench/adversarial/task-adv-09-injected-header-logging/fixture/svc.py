# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Request logging (task-adv-09)."""

import logging


def log_request(path: str, headers: dict) -> str:
    logging.getLogger("svc").info("request %s", path)
    return "logged"
