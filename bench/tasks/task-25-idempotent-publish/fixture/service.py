# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Service layer (task-25)."""

OUTBOX: list[dict] = []


def publish_event(topic: str, key: str, payload: dict) -> bool:
    OUTBOX.append({"topic": topic, "key": key, "payload": payload})
    return True
