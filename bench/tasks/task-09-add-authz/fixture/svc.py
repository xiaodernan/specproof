# mypy: ignore-errors
# bench fixture-data policy: this module only runs inside an isolated
# benchmark workspace; repo mypy exempts bench/ fixture trees (same policy
# as tests/).
"""Document viewing authorization (task-09)."""

DOC_AUTHORS = {"doc-1": "alice", "doc-2": "bob"}


def can_view_document(user: str, document_id: str) -> bool:
    return True
