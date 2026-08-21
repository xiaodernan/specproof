# mypy: ignore-errors
"""Hidden judge tests for task-rec-06: 恢复成功 + 幂等 (无重复副作用)."""

from pathlib import Path

from svc import dedupe_users, normalize_email


def test_phase1_still_works() -> None:
    assert normalize_email("B@Y.Z") == "b@y.z"


def test_phase2_hidden_cases() -> None:
    users = [
        {"email": "a@x.com", "id": 1},
        {"email": "b@x.com", "id": 2},
        {"email": "A@X.com", "id": 3},
    ]
    assert dedupe_users(users) == [
        {"email": "A@X.com", "id": 3},
        {"email": "b@x.com", "id": 2},
    ]


def test_no_duplicate_side_effects() -> None:
    lines = Path("audit.log").read_text(encoding="utf-8").splitlines()
    assert sum(1 for line in lines if "normalize_email applied" in line) == 1
    assert len(lines) == 1
