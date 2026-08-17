"""P2 unit tests — structured requirement parser."""

from agent.contracts.parser import parse_requirements

SPEC = """Requirements for the email change API:

1. Authentication
   - Must reject unauthenticated requests with 401.
   - Must not allow anonymous email changes.

2. Uniqueness
   - Email addresses must be unique across all users.
   - Attempting to change to an already-used email must be rejected.

3. Events
   - The email-changed event must be published exactly once.
"""


def test_parse_numbered_sections():
    result = parse_requirements(SPEC)
    assert len(result.requirements) == 3
    ids = [r.id for r in result.requirements]
    assert any("AUTH" in i for i in ids)
    assert any("UNIQUE" in i for i in ids)
    assert any("EVENT" in i for i in ids)


def test_acceptance_criteria_extracted():
    result = parse_requirements(SPEC)
    auth = next(r for r in result.requirements if "AUTH" in r.id)
    assert len(auth.acceptance_criteria) >= 1
    assert any("401" in ac.text for ac in auth.acceptance_criteria)


def test_forbidden_changes_extracted():
    result = parse_requirements(SPEC)
    auth = next(r for r in result.requirements if "AUTH" in r.id)
    assert any("anonymous" in f for f in auth.forbidden_changes)


def test_empty_text_is_honest():
    result = parse_requirements("")
    assert result.requirements == []
    assert result.warnings


def test_priority_derived_from_must():
    result = parse_requirements(SPEC)
    auth = next(r for r in result.requirements if "AUTH" in r.id)
    assert auth.priority == "P1"


def test_unstructured_text_becomes_single_requirement():
    result = parse_requirements("The API must stay compatible.")
    assert len(result.requirements) == 1
