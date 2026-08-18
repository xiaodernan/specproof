# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Metrics reporting (task-rec-07)."""


def collect_metrics(samples: list[float]) -> dict:
    if not samples:
        return {}
    return {"count": len(samples), "mean": sum(samples) / len(samples)}


def render_report(metrics: dict) -> str:
    raise NotImplementedError("phase 2 pending")
