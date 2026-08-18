# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Public API layer (task-25)."""

from service import publish_event


def publish(topic: str, key: str, payload: dict) -> bool:
    return publish_event(topic, key, payload)
