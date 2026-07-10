"""compile_contracts node — convert requirements into verifiable contracts.

For Phase 0, uses a rule-based parser for demo requirements.
Phase 1+ will use LLM-based compilation.
"""

import re

from agent.state import Phase0State

_CONTRACT_TEMPLATES = {
    "auth": {
        "checker_type": "http",
        "expected_behavior": "Unauthenticated requests must receive 401 Unauthorized",
    },
    "unique": {
        "checker_type": "sql",
        "expected_behavior": (
            "Duplicate email insertion must be rejected with "
            "constraint violation or application error"
        ),
    },
    "token_invalidation": {
        "checker_type": "redis",
        "expected_behavior": "After email change, old token keys must be deleted from Redis",
    },
    "backward_compatible": {
        "checker_type": "openapi",
        "expected_behavior": "API schema must remain backward-compatible between base and head",
    },
    "event_once": {
        "checker_type": "rabbitmq",
        "expected_behavior": "Email change event must be published exactly once per change",
    },
    "transaction": {
        "checker_type": "sql",
        "expected_behavior": "Email update and token invalidation must be in same transaction",
    },
}


def _parse_requirements(text: str) -> list[dict]:
    """Parse requirement text into contract candidates."""
    contracts = []
    text_lower = text.lower()

    patterns = {
        "auth": [
            r"unauthorized|unauthenticated|not logged in|without auth|401",
            r"must (be|require) (authenticated|auth|login)",
            r"@PreAuthorize|isAuthenticated",
        ],
        "unique": [
            r"unique|duplicate|already (exists|taken|used)",
            r"email.*unique|unique.*email",
        ],
        "token_invalidation": [
            r"token.*invalid|invalidate.*token|old token",
            r"session.*expire|expire.*session|redis.*delete",
        ],
        "backward_compatible": [
            r"backward.compatible|api.*compatible|schema.*compatible",
            r"openapi|swagger|breaking.change",
        ],
        "event_once": [
            r"exactly once|idempotent|duplicate.*event|event.*once",
            r"rabbitmq|message.*queue|publish.*once",
        ],
        "transaction": [
            r"transaction|atomic|rollback|@Transactional",
            r"all.or.nothing|consistency",
        ],
    }

    for contract_type, regexes in patterns.items():
        for regex in regexes:
            if re.search(regex, text_lower):
                contracts.append({
                    "id": f"{contract_type.upper()}-01",
                    "requirement": text.strip().split("\n")[0][:120],
                    "checker_type": _CONTRACT_TEMPLATES[contract_type]["checker_type"],
                    "expected_behavior": _CONTRACT_TEMPLATES[contract_type]["expected_behavior"],
                    "result": "UNVERIFIED",
                    "evidence_ref": None,
                })
                break

    return contracts


def compile_contracts_node(state: Phase0State) -> dict:
    """Compile requirements into a list of Contract dicts."""
    text = state.get("requirement_text", "")
    contracts = _parse_requirements(text)

    if not contracts:
        contracts = [{
            "id": "GENERIC-01",
            "requirement": text.strip()[:200] if text else "No requirement text provided",
            "checker_type": "http",
            "expected_behavior": "API must behave correctly per requirement",
            "result": "UNVERIFIED",
            "evidence_ref": None,
        }]

    return {"contracts": contracts}
