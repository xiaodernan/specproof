"""#96 — the Web audit view must not invent its own copy of the vocabulary.

`storage/mysql.py` stamps every `list_audit_logs` row with a
``job_disposition`` (#95), and `apps/web/src/pages/Audit.tsx` is now the first
place in the product that shows it to a human. That is exactly the seam where
#81's disease returns: a frontend that hand-types the backend's enum values
drifts the moment the backend grows one, and the reader sees a confident,
wrong label.

Both sides are parsed from their sources — the TS map and the route
handler's own `_assert_role(..., frozenset({...}))` — because a hand-copied
expectation would only re-assert what the author already believed.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LABELS = REPO / "apps" / "web" / "src" / "ui" / "auditLabels.ts"
ADMIN_ROUTE = REPO / "api" / "routes" / "admin.py"

from storage.mysql import (  # noqa: E402 — after path setup for symmetry
    AUDIT_ACTIONS,
    AUDIT_JOB_PRESENT,
    AUDIT_JOB_PURGED,
    AUDIT_JOB_SYSTEM_LEVEL,
    AUDIT_JOB_UNEXPLAINED,
)

_DISPOSITION_KEY_RE = re.compile(r"^  ([a-z_]+): \{$", re.MULTILINE)
_ROLES_RE = re.compile(r"AUDIT_ROLES: string\[\] = \[([^\]]*)\]")
_HANDLER_ROLES_RE = re.compile(
    r'@admin_router\.get\("/audit"\).*?_assert_role\(\s*principal,\s*frozenset\(\{([^}]*)\}\)',
    re.DOTALL,
)


def _labels_text() -> str:
    return LABELS.read_text(encoding="utf-8")


def fe_dispositions() -> set[str]:
    """Keys of the TS ``AUDIT_DISPOSITIONS`` map, in its own block only."""
    text = _labels_text()
    _, _, rest = text.partition("AUDIT_DISPOSITIONS: Record<string, AuditDispositionSpec> = {")
    body, _, _ = rest.partition("\n};")
    assert body, "AUDIT_DISPOSITIONS block not parsed — the probe is broken"
    return set(_DISPOSITION_KEY_RE.findall(body))


def fe_roles() -> set[str]:
    match = _ROLES_RE.search(_labels_text())
    assert match, "AUDIT_ROLES not found in auditLabels.ts"
    return {s.strip().strip('"') for s in match.group(1).split(",") if s.strip()}


def server_roles_for_audit() -> set[str]:
    match = _HANDLER_ROLES_RE.search(ADMIN_ROUTE.read_text(encoding="utf-8"))
    assert match, (
        "GET /api/v1/admin/audit no longer asserts a frozenset of roles — "
        "either the handler changed shape or the route moved; the UI gate "
        "cannot be trusted without it"
    )
    return {s.strip().strip('"') for s in match.group(1).split(",") if s.strip()}


def test_the_backend_dispositions_are_all_glossed() -> None:
    declared = {
        AUDIT_JOB_PRESENT,
        AUDIT_JOB_PURGED,
        AUDIT_JOB_SYSTEM_LEVEL,
        AUDIT_JOB_UNEXPLAINED,
    }
    assert fe_dispositions() == declared, (
        f"web-only={sorted(fe_dispositions() - declared)} "
        f"backend-only={sorted(declared - fe_dispositions())} — an auditor "
        "would see a label the store never writes, or a raw token it does"
    )


def test_every_gloss_explains_itself() -> None:
    """A label without a reason is a badge, not an audit aid."""
    text = _labels_text()
    for key in fe_dispositions():
        block = re.search(rf"^  {key}: \{{(.*?)\n  \}},", text, re.DOTALL | re.MULTILINE)
        assert block, f"{key} disappeared from the map"
        body = block.group(1)
        for field in ("label:", "hint:", "cls:"):
            assert field in body, f"AUDIT_DISPOSITIONS.{key} has no {field[:-1]}"
        assert len(re.search(r'hint: "(.*)"', body).group(1)) > 12, (
            f"{key}'s hint is too short to explain the judgement"
        )


def test_the_web_page_does_not_start_a_second_action_vocabulary() -> None:
    """Actions stay backend-declared; the page renders the token verbatim.

    A TS copy of ``AUDIT_ACTIONS`` is how #87 shipped five dead words: the
    audit *action* is the operator's own evidence, so it must not be renamed
    — and a page that renamed it would have to be kept in step forever.
    """
    text = _labels_text()
    keys = set(re.findall(r'^\s{2}"?([a-z_]+)"?:', text, re.MULTILINE))
    invented = keys & set(AUDIT_ACTIONS)
    assert not invented, (
        f"auditLabels.ts enumerates audit actions {sorted(invented)}; the "
        "declaration lives in storage/mysql.py and the page shows the token"
    )


def test_the_nav_gate_matches_the_handler() -> None:
    assert fe_roles() == server_roles_for_audit(), (
        f"UI allows {sorted(fe_roles())} but GET /admin/audit allows "
        f"{sorted(server_roles_for_audit())} — the sidebar would advertise a "
        "page that answers 403"
    )


def test_the_role_gate_is_narrower_than_billing_on_purpose() -> None:
    """The one asymmetry worth locking: operator can bill, not audit.

    If someone "harmonises" the two role sets, this test is where they learn
    the difference was measured from the handler, not copied by mistake.
    """
    roles = server_roles_for_audit()
    assert "operator" not in roles, (
        f"the audit handler now accepts operator {sorted(roles)}; update "
        "auditLabels.ts and DATA_DICTIONARY §1.8 together, not one alone"
    )
    assert roles == {"admin", "auditor"}
