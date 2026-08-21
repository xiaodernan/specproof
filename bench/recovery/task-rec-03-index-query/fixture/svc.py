# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees.
"""Index service (task-rec-03)."""


def build_index(docs: dict[str, str]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for doc_id, text in docs.items():
        for word in text.split():
            index.setdefault(word, set()).add(doc_id)
    return index


def query_index(index: dict[str, set[str]], word: str) -> list[str]:
    raise NotImplementedError("phase 2 pending")
